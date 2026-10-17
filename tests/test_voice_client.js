'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
require('../src/canvas/voice.js');

function harness(options = {}) {
    const sockets = [];
    const peers = [];
    const streams = [];
    const requests = [];
    const statuses = [];
    const audio = { srcObject: null };
    let fetchResponse = { ok: true, text: async () => 'answer-sdp' };

    class Socket {
        static OPEN = 1;
        constructor(url) {
            this.url = url;
            this.readyState = 0;
            this.sent = [];
            sockets.push(this);
            queueMicrotask(() => {
                if (this.readyState === 0) {
                    this.readyState = 1;
                    this.onopen?.();
                }
            });
        }
        send(data) { this.sent.push(JSON.parse(data)); }
        close() {
            this.readyState = 3;
            this.onclose?.();
        }
        receive(event) { this.onmessage({ data: JSON.stringify(event) }); }
    }

    class Peer {
        constructor() {
            this.connectionState = 'new';
            this.closed = false;
            peers.push(this);
        }
        createDataChannel(label) {
            this.dc = {
                label,
                readyState: 'connecting',
                sent: [],
                send(data) { this.sent.push(JSON.parse(data)); },
                receive(event) { this.onmessage({ data: JSON.stringify(event) }); },
                open() { this.readyState = 'open'; this.onopen?.(); },
            };
            return this.dc;
        }
        addTrack(track, stream) { this.track = track; this.stream = stream; }
        async createOffer() { return { type: 'offer', sdp: 'offer-sdp' }; }
        async setLocalDescription(offer) { this.localDescription = offer; }
        async setRemoteDescription(answer) {
            this.remoteDescription = answer;
            queueMicrotask(() => {
                if (this.closed) return;
                this.connectionState = 'connected';
                this.onconnectionstatechange?.();
                this.ontrack?.({ streams: [{ id: 'remote-' + peers.indexOf(this) }] });
                if (!options.holdChannel) this.dc.open();
            });
        }
        close() {
            this.closed = true;
            this.connectionState = 'closed';
            this.onconnectionstatechange?.();
        }
    }

    function newStream() {
        const track = { stopped: false, stop() { this.stopped = true; } };
        const stream = {
            track,
            getAudioTracks() { return [track]; },
            getTracks() { return [track]; },
        };
        streams.push(stream);
        return stream;
    }

    const client = new globalThis.ADCVoiceClient({
        sessionId: 'test-session',
        getAudioOutput: () => audio,
        onStatus: (state, detail) => statuses.push({ state, detail }),
        inject: {
            WebSocket: Socket,
            RTCPeerConnection: Peer,
            openMediaStream: options.openMediaStream || (() => Promise.resolve(newStream())),
            setTimeout: options.setTimeout,
            clearTimeout: options.clearTimeout,
            fetch: async (url, init) => {
                requests.push({ url, init });
                return fetchResponse;
            },
        },
    });
    return {
        client, sockets, peers, streams, requests, statuses, audio, newStream,
        setFetchResponse(value) { fetchResponse = value; },
    };
}

async function settle() {
    for (let i = 0; i < 3; i++) await new Promise(resolve => setImmediate(resolve));
}

async function bootstrap(h) {
    await h.client.start();
    h.sockets[0].receive({
        type: 'ag2.init',
        config: { client_secret: { value: 'ephemeral-test-token' }, model: 'test-model' },
    });
    await settle();
}

test('bootstraps SDP with ephemeral token and waits for data channel', async () => {
    const h = harness({ holdChannel: true });
    await bootstrap(h);
    assert.equal(h.sockets[0].url, 'ws:///voice?session_id=test-session');
    assert.equal(h.requests[0].url, 'https://api.openai.com/v1/realtime/calls');
    assert.equal(h.requests[0].init.headers.Authorization, 'Bearer ephemeral-test-token');
    assert.equal(h.requests[0].init.body, 'offer-sdp');
    assert.equal(h.peers[0].remoteDescription.sdp, 'answer-sdp');
    assert.equal(h.client.pc, null);
    h.sockets[0].receive({ type: 'adc.narrate_results',
                           results: [{ summary: 'Queued before ready', urgency: 'normal' }] });
    h.peers[0].dc.open();
    await settle();
    assert.equal(h.client.pc, h.peers[0]);
    assert.equal(h.client.dc.sent[0].item.content[0].text.includes('Queued before ready'), true);
    assert.equal(h.client.dc.sent[1].type, 'response.create');
    assert.equal(h.audio.srcObject.id, 'remote-0');
    assert.equal(h.statuses.at(-1).state, 'connected');
    h.client.stop();
});

test('relays tool call, result, narration, and completed turn', async () => {
    const h = harness();
    await bootstrap(h);
    const dc = h.client.dc;
    dc.receive({ type: 'response.function_call_arguments.done', name: 'dispatch_intent',
                 call_id: 'call-1', arguments: '{"utterance":"hello"}', event_id: 'event-1',
                 response_id: 'response-1', item_id: 'item-1', output_index: 0 });
    assert.deepEqual(h.sockets[0].sent.at(-1), {
        type: 'response.function_call_arguments.done', name: 'dispatch_intent',
        call_id: 'call-1', arguments: '{"utterance":"hello"}', event_id: 'event-1',
    });
    h.sockets[0].receive({ type: 'conversation.item.create',
                           item: { type: 'function_call_output', call_id: 'call-1', output: 'ack' } });
    assert.equal(dc.sent.at(-2).item.output, 'ack');
    assert.equal(dc.sent.at(-1).type, 'response.create');
    h.sockets[0].receive({ type: 'adc.narrate_results',
                           results: [{ summary: 'Finished', urgency: 'high' }] });
    assert.equal(dc.sent.at(-2).type, 'conversation.item.create');
    assert.equal(dc.sent.at(-1).type, 'response.create');
    dc.receive({ type: 'conversation.item.input_audio_transcription.completed', transcript: 'hello' });
    dc.receive({ type: 'response.output_audio_transcript.done', transcript: 'done' });
    dc.receive({ type: 'response.done' });
    assert.deepEqual(h.sockets[0].sent.at(-1), {
        type: 'adc.turn_done', user_text: 'hello', assistant_text: 'done',
    });
    h.client.stop();
});

test('replaces a peer and preserves the old peer on failed replacement', async () => {
    const h = harness();
    await bootstrap(h);
    const old = h.peers[0];
    h.sockets[0].receive({ type: 'adc.session_update', request_id: 'change-1', voice: 'coral',
                           config: { client_secret: { value: 'next-token' }, model: 'test-model' } });
    await settle();
    assert.equal(h.client.pc, h.peers[1]);
    assert.equal(old.closed, true);
    assert.equal(h.streams[0].track.stopped, true);
    assert.deepEqual(h.sockets[0].sent.at(-1), {
        type: 'adc.session_updated', request_id: 'change-1', voice: 'coral',
    });
    h.sockets[0].receive({ type: 'adc.session_update_applied', request_id: 'change-1', voice: 'coral' });
    const active = h.client.pc;
    h.setFetchResponse({ ok: false, status: 503 });
    h.sockets[0].receive({ type: 'adc.session_update', request_id: 'change-2', voice: 'sage',
                           config: { client_secret: { value: 'third-token' }, model: 'test-model' } });
    await settle();
    assert.equal(h.client.pc, active);
    assert.equal(active.closed, false);
    assert.equal(h.peers[2].closed, true);
    assert.equal(h.streams[2].track.stopped, true);
    assert.deepEqual(h.sockets[0].sent.at(-1), {
        type: 'adc.session_update_failed', request_id: 'change-2',
    });
    h.client.stop();
});

test('cleans a failed bootstrap and late microphone permission after stop', async () => {
    const h = harness();
    h.setFetchResponse({ ok: false, status: 401 });
    await bootstrap(h);
    assert.equal(h.client.state, 'failed');
    assert.equal(h.peers[0].closed, true);
    assert.equal(h.streams[0].track.stopped, true);
    assert.equal(h.sockets[0].readyState, 3);

    let releaseMic;
    const late = harness({ openMediaStream: () => new Promise(resolve => { releaseMic = resolve; }) });
    await late.client.start();
    late.sockets[0].receive({ type: 'ag2.init',
        config: { client_secret: { value: 'ephemeral-test-token' }, model: 'test-model' } });
    await settle();
    late.client.stop();
    const stream = late.newStream();
    releaseMic(stream);
    await settle();
    assert.equal(stream.track.stopped, true);
    assert.equal(late.peers[0].closed, true);
    assert.equal(late.client.pc, null);
    assert.equal(late.client.state, 'closed');
});

test('replacement deadline closes only the candidate and reports failure', async () => {
    const timers = [];
    const h = harness({
        holdChannel: true,
        setTimeout(fn) {
            const timer = { fn, cleared: false };
            timers.push(timer);
            return timer;
        },
        clearTimeout(timer) { timer.cleared = true; },
    });
    await bootstrap(h);
    h.peers[0].dc.open();
    await settle();
    const old = h.client.pc;
    h.sockets[0].receive({ type: 'adc.session_update', request_id: 'slow-change', voice: 'sage',
                           config: { client_secret: { value: 'next-token' }, model: 'test-model' } });
    await settle();
    assert.equal(h.client.pc, old);
    assert.equal(timers[0].cleared, true);
    assert.equal(timers[1].cleared, false);
    timers[1].fn();
    await settle();
    assert.equal(h.client.pc, old);
    assert.equal(old.closed, false);
    assert.equal(h.peers[1].closed, true);
    assert.equal(h.streams[1].track.stopped, true);
    assert.deepEqual(h.sockets[0].sent.at(-1), {
        type: 'adc.session_update_failed', request_id: 'slow-change',
    });
    h.client.stop();
});

test('start settles when the socket closes before opening', async () => {
    const h = harness();
    const starting = h.client.start();
    h.sockets[0].close();
    await starting;
    assert.equal(h.client.state, 'closed');
    assert.equal(h.client.ws, null);
});

test('waits briefly for a late user transcript and skips tool-only turns', async () => {
    const timers = [];
    const h = harness({
        setTimeout(fn, ms) {
            const timer = { fn, ms, cleared: false };
            timers.push(timer);
            return timer;
        },
        clearTimeout(timer) { timer.cleared = true; },
    });
    await bootstrap(h);
    const dc = h.client.dc;
    dc.receive({ type: 'response.done' });
    const toolOnlyTimer = timers.at(-1);
    assert.equal(toolOnlyTimer.ms, 1000);
    toolOnlyTimer.fn();
    assert.equal(h.sockets[0].sent.filter(e => e.type === 'adc.turn_done').length, 0);

    dc.receive({ type: 'response.output_audio_transcript.done', transcript: 'I can help.' });
    dc.receive({ type: 'response.done' });
    const turnTimer = timers.at(-1);
    assert.equal(h.sockets[0].sent.filter(e => e.type === 'adc.turn_done').length, 0);
    dc.receive({ type: 'conversation.item.input_audio_transcription.completed', transcript: 'Help me.' });
    assert.deepEqual(h.sockets[0].sent.at(-1), {
        type: 'adc.turn_done', user_text: 'Help me.', assistant_text: 'I can help.',
    });
    assert.equal(turnTimer.cleared, true);
    assert.equal(h.sockets[0].sent.filter(e => e.type === 'adc.turn_done').length, 1);
    h.client.stop();
});

test('keeps the user transcript across an intermediate tool response', async () => {
    const timers = [];
    const h = harness({
        setTimeout(fn, ms) {
            const timer = { fn, ms, cleared: false };
            timers.push(timer);
            return timer;
        },
        clearTimeout(timer) { timer.cleared = true; },
    });
    await bootstrap(h);
    const dc = h.client.dc;
    dc.receive({ type: 'conversation.item.input_audio_transcription.completed',
                 transcript: 'What is the status?' });
    dc.receive({ type: 'response.done', response: {
        output: [{ type: 'function_call', name: 'dispatch_intent', call_id: 'call-1' }],
    } });
    assert.equal(timers.filter(timer => timer.ms === 1000).length, 0);
    assert.equal(h.sockets[0].sent.filter(e => e.type === 'adc.turn_done').length, 0);

    dc.receive({ type: 'response.output_audio_transcript.done', transcript: 'On it. Healthy.' });
    dc.receive({ type: 'response.done', response: { output: [{ type: 'message' }] } });
    assert.deepEqual(h.sockets[0].sent.at(-1), {
        type: 'adc.turn_done',
        user_text: 'What is the status?',
        assistant_text: 'On it. Healthy.',
    });
    assert.equal(h.sockets[0].sent.filter(e => e.type === 'adc.turn_done').length, 1);
    h.client.stop();
});
