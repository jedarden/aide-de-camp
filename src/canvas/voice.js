/**
 * ADC voice client — the browser half of the Phase 4 WebRTC flow.
 *
 * Sequence (see README-PHASE4.md "WebRTC bootstrap"):
 *
 *   1. Open the ADC /voice WebSocket (?session_id=...).
 *   2. Server exchanges its OPENAI_API_KEY for an ephemeral Realtime token
 *      server-side and replies with `ag2.init` carrying ONLY
 *      {client_secret, model}. The API key never crosses this socket.
 *   3. Create an RTCPeerConnection + mic track + "oai-events" data channel,
 *      POST the SDP offer to the OpenAI Realtime endpoint authenticated with
 *      the *ephemeral* token, and apply the SDP answer.
 *   4. Relay: Realtime data-channel events the server understands go to the
 *      ADC socket; ADC server events (tool results, narration, voice
 *      replacement) go onto the data channel.
 *
 * Timeout and failure behavior (mirrors the server side):
 *   - PEER_CONNECT_TIMEOUT_MS: a peer must reach "connected" within 15s of
 *     ag2.init (or of an adc.session_update). On expiry the peer is torn
 *     down, the server is told via an `error` event, the socket is closed,
 *     and the UI sees onStatus("failed", reason).
 *   - An SDP exchange failure (non-2xx from the Realtime endpoint) fails the
 *     bootstrap immediately with the same teardown path.
 *   - During a voice replacement the OLD peer stays live until the new one
 *     connects, so a failed replacement never interrupts playback; the
 *     server gets adc.session_update_failed and keeps the old voice.
 *
 * No imports: this file is loaded as a plain <script> (like canvas.js) and
 * attaches ADCVoiceClient to the global object, so it stays loadable under
 * Node for syntax/contract checks without a browser.
 */
"use strict";
(function (global) {
    /** Milliseconds a WebRTC peer has to reach the "connected" state. */
    var PEER_CONNECT_TIMEOUT_MS = 15000;
    var TURN_COMPLETION_GRACE_MS = 1000;
    /** OpenAI Realtime WebRTC SDP-exchange endpoint (browser → OpenAI leg). */
    var REALTIME_BASE_URL = "https://api.openai.com/v1/realtime/calls";
    /** Data channel the Realtime API delivers its events on. */
    var REALTIME_DC_LABEL = "oai-events";

    /**
     * @param {object} opts
     * @param {string} opts.sessionId           ADC session id (?session_id=)
     * @param {function(): HTMLAudioElement} [opts.getAudioOutput]
     *        Supplies the autoplay <audio> element for remote playback.
     * @param {function(string, string=)} [opts.onStatus]
     *        state, detail — one of connecting|connected|failed|closed|error.
     * @param {function(object)} [opts.onServerError] Server sent an `error` event.
     * @param {object} [opts.inject] Test seam: {RTCPeerConnection, fetch,
     *        openMediaStream, WebSocket, timers} overrides.
     */
    function AdcVoiceClient(opts) {
        opts = opts || {};
        this.sessionId = opts.sessionId;
        this.getAudioOutput = opts.getAudioOutput || defaultAudioOutput;
        this.onStatus = opts.onStatus || function () {};
        this.onServerError = opts.onServerError || function () {};

        var inject = opts.inject || {};
        this.RTCPeerConnection = inject.RTCPeerConnection ||
            (typeof RTCPeerConnection !== "undefined" ? RTCPeerConnection : null);
        this.fetchImpl = inject.fetch || global.fetch.bind(global);
        this.openMediaStream = inject.openMediaStream || openMicStream;
        this.WebSocketImpl = inject.WebSocket || global.WebSocket;
        this.setTimeoutImpl = inject.setTimeout || setTimeoutProto();
        this.clearTimeoutImpl = inject.clearTimeout || global.clearTimeout.bind(global);

        this.ws = null;
        this.pc = null;          // active RTCPeerConnection
        this.dc = null;          // its "oai-events" data channel
        this.micStream = null;
        this.model = null;
        this._replacement = null; // pending adc.session_update being applied
        this._pendingPeers = new Set();
        this._generation = 0;
        this._audioOutput = null;
        this._realtimeQueue = [];
        this._turn = { userText: "", assistantText: "" };
        this._turnTimer = null;
        this._closingWs = false;
    }

    /* ------------------------------------------------------------------ */
    /* Public API                                                          */
    /* ------------------------------------------------------------------ */

    /** Open the socket and bootstrap the first WebRTC peer. */
    AdcVoiceClient.prototype.start = function () {
        if (this.ws) return Promise.resolve();
        this._status("connecting");
        return this._connectWebSocket();
    };

    /** Tear down the peer and the socket. Safe to call twice. */
    AdcVoiceClient.prototype.stop = function () {
        this._generation++;
        this._cancelPendingPeers();
        this._replacement = null;
        this._clearTurnTimer();
        this._turn = { userText: "", assistantText: "" };
        this._realtimeQueue = [];
        this._teardownPeer();
        if (this.ws) {
            this._closingWs = true;
            try { this.ws.close(); } catch (e) { /* already closed */ }
            this.ws = null;
        }
        this._status("closed");
    };

    /** Tell the server the user moved between surfaces (audio ↔ canvas). */
    AdcVoiceClient.prototype.surfaceSwitch = function (surface) {
        this._sendToServer({ type: "adc.surface_switch", surface: surface });
    };

    /* ------------------------------------------------------------------ */
    /* WebSocket leg (browser ↔ ADC server)                                */
    /* ------------------------------------------------------------------ */

    AdcVoiceClient.prototype._connectWebSocket = function () {
        var self = this;
        var url = voiceSocketUrl(this.sessionId);
        this._closingWs = false;
        return new Promise(function (resolve) {
            var ws;
            try {
                ws = new self.WebSocketImpl(url);
            } catch (err) {
                self._fail("socket", "cannot open /voice socket: " + err.message);
                resolve();
                return;
            }
            self.ws = ws;
            ws.onopen = function () { resolve(); };
            ws.onerror = function () {
                resolve();
                if (self.ws !== ws) return;
                if (!self.pc) self._fail("socket", "/voice socket error");
            };
            ws.onclose = function () {
                resolve();
                if (self.ws !== ws) return;
                self._generation++;
                self._cancelPendingPeers();
                self._clearTurnTimer();
                self._turn = { userText: "", assistantText: "" };
                self._realtimeQueue = [];
                self._teardownPeer();
                if (!self._closingWs && self.state !== "error") {
                    self._status("closed", "socket closed");
                }
                self.ws = null;
            };
            ws.onmessage = function (msg) { self._handleServerEvent(msg.data); };
        });
    };

    AdcVoiceClient.prototype._handleServerEvent = function (raw) {
        var ev;
        try { ev = JSON.parse(raw); } catch (e) { return; }
        switch (ev.type) {
            case "ag2.init":
                this.model = ev.config && ev.config.model;
                var generation = this._generation;
                this._bootstrapPeer(ev.config).then(function (built) {
                    if (generation === this._generation) {
                        this._activatePeer(built);
                        this._status("connected", "model " + ev.config.model);
                    } else {
                        this._disposePeer(built);
                    }
                }.bind(this)).catch(function (err) {
                    if (generation === this._generation) {
                        this._fail(err.code || "bootstrap", err);
                    }
                }.bind(this));
                break;
            case "adc.session_update":
                this._replacePeer(ev);
                break;
            case "adc.session_update_applied":
                this._replacement = null;
                this._status("connected", "voice is now " + ev.voice);
                break;
            case "adc.session_update_rejected":
                this._replacement = null;
                this._cancelPendingPeers();
                this._status("connected", "voice change rejected: " + ev.reason);
                break;
            case "adc.narrate_results":
                this._narrateResults(ev);
                break;
            case "conversation.item.create":
                // A function-call result needs a new response to let the model
                // continue the turn after it receives the output.
                this._sendToRealtime(ev);
                this._sendToRealtime({ type: "response.create" });
                break;
            case "adc.surface_switch_ack":
                this._status("connected", ev.summary);
                break;
            case "error":
                this.onServerError(ev);
                this._status("error", errorText(ev));
                break;
            default:
                break;
        }
    };

    AdcVoiceClient.prototype._sendToServer = function (payload) {
        if (this.ws && this.ws.readyState === this.WebSocketImpl.OPEN) {
            this.ws.send(JSON.stringify(payload));
        }
    };

    /* ------------------------------------------------------------------ */
    /* WebRTC leg (browser ↔ OpenAI Realtime, ephemeral-token auth)        */
    /* ------------------------------------------------------------------ */

    AdcVoiceClient.prototype._bootstrapPeer = function (config) {
        var self = this;
        var secret = config && config.client_secret && config.client_secret.value;
        if (!secret || !config.model) {
            return Promise.reject(new Error("ag2.init config missing client_secret/model"));
        }
        if (!this.RTCPeerConnection) {
            return Promise.reject(new Error("RTCPeerConnection unavailable"));
        }
        var built;
        try {
            built = this._establishPeer();
        } catch (err) {
            return Promise.reject(err);
        }
        this._pendingPeers.add(built);
        var deadline = new Promise(function (resolve, reject) {
            built.timer = self.setTimeoutImpl(function () {
                self._disposePeer(built);
                var err = new Error("peer not connected within " + PEER_CONNECT_TIMEOUT_MS + "ms");
                err.code = "webrtc_bootstrap_timeout";
                reject(err);
            }, PEER_CONNECT_TIMEOUT_MS);
        });
        var setup = Promise.resolve().then(function () {
            return self.openMediaStream();
        }).then(function (stream) {
            // A permission dialog can finish after stop() or the deadline.
            if (built.cancelled) {
                stopStream(stream);
                throw new Error("peer setup cancelled");
            }
            built.micStream = stream;
            var track = stream && stream.getAudioTracks && stream.getAudioTracks()[0];
            if (!track) throw new Error("microphone stream has no audio track");
            built.pc.addTrack(track, stream);
            return built.pc.createOffer();
        }).then(function (offer) {
            if (built.cancelled) throw new Error("peer setup cancelled");
            return built.pc.setLocalDescription(offer);
        }).then(function () {
            if (built.cancelled) throw new Error("peer setup cancelled");
            return exchangeSdp(built, secret, self.fetchImpl);
        }).then(function () {
            if (built.cancelled) throw new Error("peer setup cancelled");
            return waitUntilConnected(built);
        });
        return Promise.race([setup, deadline]).then(function () {
            if (built.cancelled) throw new Error("peer setup cancelled");
            self._pendingPeers.delete(built);
            self.clearTimeoutImpl(built.timer);
            built.timer = null;
            return built;
        }, function (err) {
            self._disposePeer(built);
            throw err;
        });
    };

    /** Build a peer. The caller owns it until activation. */
    AdcVoiceClient.prototype._establishPeer = function () {
        var self = this;
        var pc = new this.RTCPeerConnection(null);
        var dc;
        try {
            dc = pc.createDataChannel(REALTIME_DC_LABEL);
        } catch (err) {
            closePeer(pc);
            throw err;
        }
        var built = { pc: pc, dc: dc, micStream: null, remoteStream: null,
                      timer: null, cancelled: false,
                      abortController: typeof AbortController === "function" ?
                          new AbortController() : null };
        dc.onmessage = function (msg) {
            if (self.dc === dc) self._handleRealtimeEvent(msg.data);
        };
        dc.onclose = function () {
            if (self.dc === dc && self.state !== "closed") {
                self._fail("data_channel", "Realtime data channel closed");
            }
        };
        pc.ontrack = function (event) {
            if (built.cancelled || !event.streams || !event.streams[0]) return;
            built.remoteStream = event.streams[0];
            if (self.pc === pc) self._attachAudio(built.remoteStream);
        };
        return built;
    };

    AdcVoiceClient.prototype._attachAudio = function (stream) {
        if (!this._audioOutput) this._audioOutput = this.getAudioOutput();
        if (this._audioOutput) this._audioOutput.srcObject = stream;
    };

    AdcVoiceClient.prototype._activatePeer = function (built) {
        this.pc = built.pc;
        this.dc = built.dc;
        this.micStream = built.micStream;
        if (built.remoteStream) this._attachAudio(built.remoteStream);
        var queued = this._realtimeQueue;
        this._realtimeQueue = [];
        for (var i = 0; i < queued.length; i++) this._sendToRealtime(queued[i]);
    };

    /**
     * Voice replacement (adc.session_update): establish the replacement peer
     * FIRST, keep the old one audible until the new one connects, then swap.
     * Success → adc.session_updated; any failure → adc.session_update_failed
     * and the old peer stays live.
     */
    AdcVoiceClient.prototype._replacePeer = function (ev) {
        var self = this;
        var old = { pc: this.pc, dc: this.dc, micStream: this.micStream };
        this._replacement = ev.request_id;
        this._status("connecting", "switching voice to " + ev.voice);
        var generation = this._generation;
        this._bootstrapPeer(ev.config).then(function (built) {
            if (generation !== self._generation || self._replacement !== ev.request_id) {
                self._disposePeer(built);
                return;
            }
            // New peer is connected: retire the old one and confirm.
            self._activatePeer(built);
            if (old.pc && old.pc !== self.pc) closePeer(old.pc);
            if (old.micStream && old.micStream !== self.micStream) {
                stopStream(old.micStream);
            }
            self._sendToServer({
                type: "adc.session_updated",
                request_id: ev.request_id,
                voice: ev.voice
            });
        }).catch(function (err) {
            if (generation !== self._generation || self._replacement !== ev.request_id) return;
            self._replacement = null;
            self._sendToServer({
                type: "adc.session_update_failed",
                request_id: ev.request_id
            });
            self._status("connected", "voice switch failed: " + err.message);
        });
    };

    /* ------------------------------------------------------------------ */
    /* Realtime data-channel leg                                           */
    /* ------------------------------------------------------------------ */

    AdcVoiceClient.prototype._handleRealtimeEvent = function (raw) {
        var ev;
        try { ev = JSON.parse(raw); } catch (e) { return; }

        switch (ev.type) {
            case "response.function_call_arguments.done":
                // Realtime adds response/item indices that ADC's strict client
                // event schema does not accept. Relay only the tool-call fields.
                var call = {
                    type: ev.type,
                    call_id: ev.call_id,
                    name: ev.name,
                    arguments: ev.arguments
                };
                if (ev.event_id) call.event_id = ev.event_id;
                this._sendToServer(call);
                break;
            case "output_audio_buffer.started":
                this._sendToServer({ type: "adc.speaking_started" });
                break;
            case "output_audio_buffer.stopped":
                this._sendToServer({ type: "adc.speaking_stopped" });
                break;
            case "conversation.item.input_audio_transcription.completed":
            case "conversation.item.input_audio_transcription.done":
                this._turn.userText = (ev.transcript || "").trim();
                if (this._turnTimer && this._turn.assistantText) this._finishTurn();
                break;
            case "response.output_audio_transcription.completed":
            case "response.output_audio_transcription.done":
            case "response.output_audio_transcript.done":
                this._turn.assistantText = (ev.transcript || "").trim();
                if (this._turnTimer && this._turn.userText) this._finishTurn();
                break;
            case "response.done":
                // A tool-call response is an intermediate step in the same
                // user turn. Keep its transcript until the follow-up spoken
                // response finishes, then send one adc.turn_done.
                var output = ev.response && ev.response.output;
                if (Array.isArray(output) && output.some(function (item) {
                    return item.type === "function_call";
                })) break;
                if (this._turn.userText && this._turn.assistantText) {
                    this._finishTurn();
                } else if (!this._turnTimer) {
                    var self = this;
                    this._turnTimer = this.setTimeoutImpl(function () {
                        self._finishTurn();
                    }, TURN_COMPLETION_GRACE_MS);
                }
                break;
            default:
                break;
        }
    };

    AdcVoiceClient.prototype._clearTurnTimer = function () {
        if (this._turnTimer !== null) this.clearTimeoutImpl(this._turnTimer);
        this._turnTimer = null;
    };

    AdcVoiceClient.prototype._finishTurn = function () {
        this._clearTurnTimer();
        if (this._turn.userText || this._turn.assistantText) {
            this._sendToServer({
                type: "adc.turn_done",
                user_text: this._turn.userText,
                assistant_text: this._turn.assistantText
            });
        }
        this._turn = { userText: "", assistantText: "" };
    };

    AdcVoiceClient.prototype._sendToRealtime = function (payload) {
        if (this.dc && this.dc.readyState === "open") {
            try {
                this.dc.send(JSON.stringify(payload));
            } catch (err) {
                this._fail("data_channel", err);
            }
        } else if (this.state !== "closed" && this.state !== "failed") {
            this._realtimeQueue.push(payload);
        }
    };

    /** Deliver narration results into the model context, then ask it to speak. */
    AdcVoiceClient.prototype._narrateResults = function (ev) {
        var lines = (ev.results || []).map(function (r) {
            return r.summary ? ("[" + (r.urgency || "normal") + "] " + r.summary) : null;
        }).filter(Boolean);
        if (!lines.length) return;
        this._sendToRealtime({
            type: "conversation.item.create",
            item: {
                type: "message",
                role: "user",
                content: [{
                    type: "input_text",
                    text: "[ADC narration queue — narrate these results now, " +
                          "following your narration style rules]\n" + lines.join("\n")
                }]
            }
        });
        this._sendToRealtime({ type: "response.create" });
    };

    /* ------------------------------------------------------------------ */
    /* Timeout / failure plumbing                                          */
    /* ------------------------------------------------------------------ */

    AdcVoiceClient.prototype._disposePeer = function (built) {
        if (built.cancelled) return;
        built.cancelled = true;
        this._pendingPeers.delete(built);
        if (built.timer !== null) this.clearTimeoutImpl(built.timer);
        built.timer = null;
        if (built.abortController) built.abortController.abort();
        closePeer(built.pc);
        stopStream(built.micStream);
    };

    AdcVoiceClient.prototype._cancelPendingPeers = function () {
        var self = this;
        Array.from(this._pendingPeers).forEach(function (built) {
            self._disposePeer(built);
        });
    };

    /** Single teardown path for any bootstrap/transport failure. */
    AdcVoiceClient.prototype._fail = function (code, message) {
        if (this.state === "failed" || this.state === "closed") return;
        this._generation++;
        this._cancelPendingPeers();
        this._replacement = null;
        this._clearTurnTimer();
        this._turn = { userText: "", assistantText: "" };
        this._realtimeQueue = [];
        this._teardownPeer();
        this._sendToServer({
            type: "error",
            error: { code: String(code), message: String(message) }
        });
        if (this.ws) {
            this._closingWs = true;
            try { this.ws.close(); } catch (e) { /* already closed */ }
            this.ws = null;
        }
        this._status("failed", message);
    };

    AdcVoiceClient.prototype._teardownPeer = function () {
        var pc = this.pc;
        var stream = this.micStream;
        this.pc = null;
        this.dc = null;
        this.micStream = null;
        if (pc) closePeer(pc);
        if (stream) stopStream(stream);
        if (this._audioOutput) this._audioOutput.srcObject = null;
    };

    AdcVoiceClient.prototype._status = function (state, detail) {
        this.state = state;
        try { this.onStatus(state, detail); } catch (e) { /* UI errors are not ours */ }
    };

    /* ------------------------------------------------------------------ */
    /* Helpers (module-private)                                            */
    /* ------------------------------------------------------------------ */

    function defaultAudioOutput() {
        var el = document.createElement("audio");
        el.autoplay = true;
        return el;
    }

    function openMicStream() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            return Promise.reject(new Error("getUserMedia unavailable"));
        }
        return navigator.mediaDevices.getUserMedia({ audio: true });
    }

    function setTimeoutProto() {
        return function (fn, ms) { return setTimeout(fn, ms); };
    }

    function voiceSocketUrl(sessionId) {
        var proto = global.location && global.location.protocol === "https:" ? "wss" : "ws";
        var host = global.location ? global.location.host : "";
        var query = sessionId ? ("?session_id=" + encodeURIComponent(sessionId)) : "";
        return proto + "://" + host + "/voice" + query;
    }

    /** POST the local SDP offer, apply the SDP answer (ephemeral-token auth). */
    function exchangeSdp(built, secret, fetchImpl) {
        var pc = built.pc;
        return fetchImpl(REALTIME_BASE_URL, {
            method: "POST",
            body: pc.localDescription.sdp,
            signal: built.abortController ? built.abortController.signal : undefined,
            headers: {
                "Authorization": "Bearer " + secret,
                "Content-Type": "application/sdp"
            }
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error(
                    "Realtime SDP exchange failed: HTTP " + resp.status
                );
            }
            return resp.text();
        }).then(function (answerSdp) {
            return pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
        }).then(function () {
            return built;
        });
    }

    /** Resolve only when both the peer and its event channel are ready. */
    function waitUntilConnected(built) {
        var pc = built.pc;
        var dc = built.dc;
        return new Promise(function (resolve, reject) {
            function check() {
                if (built.cancelled) {
                    reject(new Error("peer setup cancelled"));
                } else if (pc.connectionState === "failed" ||
                           pc.connectionState === "closed" ||
                           pc.connectionState === "disconnected") {
                    reject(new Error("peer connection " + pc.connectionState));
                } else if (dc.readyState === "closed" || dc.readyState === "closing") {
                    reject(new Error("Realtime data channel closed"));
                } else if ((pc.connectionState === "connected" ||
                            pc.connectionState === "completed") &&
                           dc.readyState === "open") {
                    resolve(built);
                }
            }
            pc.onconnectionstatechange = check;
            dc.onopen = check;
            var previousClose = dc.onclose;
            dc.onclose = function () {
                if (previousClose) previousClose();
                check();
            };
            dc.onerror = function () { reject(new Error("Realtime data channel error")); };
            check();
        });
    }

    function attachRemoteAudio(pc, getAudioOutput) {
        pc.ontrack = function (event) {
            var el = getAudioOutput();
            if (el && event.streams && event.streams[0]) el.srcObject = event.streams[0];
        };
    }

    function closePeer(pc) {
        try { pc.close(); } catch (e) { /* already closed */ }
    }

    function stopStream(stream) {
        var tracks = (stream && stream.getTracks) ? stream.getTracks() : [];
        tracks.forEach(function (t) { t.stop(); });
    }

    function errorText(ev) {
        if (typeof ev.error === "string") return ev.error;
        if (ev.error && ev.error.message) return ev.error.message;
        return "server error";
    }

    AdcVoiceClient.PEER_CONNECT_TIMEOUT_MS = PEER_CONNECT_TIMEOUT_MS;
    AdcVoiceClient.REALTIME_BASE_URL = REALTIME_BASE_URL;

    global.ADCVoiceClient = AdcVoiceClient;
})(typeof window !== "undefined" ? window : globalThis);
