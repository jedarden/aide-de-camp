# adc-3wnm3: Wire elapsed time updates with tickPendingElapsed()

## Task Summary

Wire elapsed time counter updates to pending cards so users can see how long requests have been in flight.

## Implementation Status

**ALREADY COMPLETE** - this functionality was implemented in a previous change.

### Evidence from codebase:

1. **Periodic timer setup** (`src/canvas/index.html` lines 951-959):
   ```javascript
   setInterval(function () {
       var now = Date.now();
       var pendingCards = document.querySelectorAll('.pending-card[data-pending-id]');
       pendingCards.forEach(function (card) {
           tickPendingElapsed(card, now);
           applyAgedTreatment(card, now);
       });
   }, 1000);
   ```

2. **tickPendingElapsed() function** (`src/canvas/canvas.js` lines 423-429):
   ```javascript
   function tickPendingElapsed(card, now) {
       const createdAt = parseInt(card.dataset.createdAt, 10) || 0;
       const elapsedMs = Math.max(0, (now || 0) - createdAt);
       const node = card.querySelector('.pending-elapsed');
       if (node) node.textContent = formatElapsed(elapsedMs) + ' elapsed';
       return elapsedMs;
   }
   ```

3. **Human-readable format** (`src/canvas/canvas.js` lines 158-165):
   ```javascript
   function formatElapsed(ms) {
       const s = Math.max(0, Math.floor((ms || 0) / 1000));
       if (s < 60) return s + 's';
       const m = Math.floor(s / 60);
       const rem = s % 60;
       return m + 'm ' + (rem < 10 ? '0' : '') + rem + 's';
   }
   ```

4. **Elapsed element in pending cards** (`src/canvas/canvas.js` lines 391-394):
   ```javascript
   const elapsed = el('div', 'pending-elapsed', [
       formatElapsed(0) + ' elapsed'
   ]);
   card.appendChild(elapsed);
   ```

### All Acceptance Criteria Met:
- ✅ tickPendingElapsed() called periodically (setInterval every 1s)
- ✅ Elapsed time counter appears on pending cards  
- ✅ Format is human-readable ("12s elapsed", "1m 05s elapsed")
- ✅ Updates stop when card completes (pending cards are replaced)

## Server Issue (Unrelated)

The server failed to start due to a database migration error:
```
sqlite3.IntegrityError: NOT NULL constraint failed: results_new.created_at
```

This is in `src/session/store.py` line 449 and needs to be fixed separately - it's unrelated to the elapsed time functionality which is purely client-side.
