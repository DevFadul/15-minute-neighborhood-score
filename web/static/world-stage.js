(function () {
  if (customElements.get('world-stage')) return;
  var THREE_URL = 'https://unpkg.com/three@0.184.0/build/three.module.js';

  // The scene is in real metres: 1 world unit = 1 m. Building footprints and
  // heights come straight from OpenStreetMap in metres, facility markers sit at
  // their true distance on their true compass bearing, and the walker is
  // human-sized -- so a 300 m tower really does tower over you.
  var WALK_M_PER_MIN = 80;   // matches geocoding.py's WALK_METERS_PER_MINUTE
  var DETOUR = 1.3;          // matches geocoding.py's DETOUR_FACTOR, so the live
                             // readout agrees with the minutes the server scored
  var MOVE_SPEED = 11;       // m/s -- brisk enough to cross the map without waiting
  var WORLD_LIMIT = 1600;    // how far the walker may roam from the origin
  var MARKER_POLE_H = 30;
  var LABEL_H = 38;

  function rng(seed) {
    var s = seed >>> 0 || 1;
    return function () { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  }
  function hash(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function fmtMetres(m) {
    return m >= 1000 ? (m / 1000).toFixed(1) + ' km' : Math.round(m) + ' m';
  }

  function labelSprite(THREE, cat) {
    var c = document.createElement('canvas');
    c.width = 512; c.height = 150;
    var g = c.getContext('2d');
    g.fillStyle = '#faf6ec';
    g.fillRect(0, 0, 512, 150);
    g.strokeStyle = cat.color; g.lineWidth = 10;
    g.strokeRect(5, 5, 502, 140);
    g.fillStyle = cat.color;
    g.fillRect(5, 5, 96, 140);
    g.fillStyle = '#faf6ec';
    g.font = '700 64px "IBM Plex Mono", monospace';
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(cat.letter, 53, 78);
    g.fillStyle = '#221b12';
    g.textAlign = 'left';
    g.font = '700 40px "Public Sans", system-ui, sans-serif';
    var title = (cat.name || cat.short || '').toUpperCase();
    if (title.length > 17) title = title.slice(0, 16) + '…';
    g.fillText(title, 124, 52);
    g.fillStyle = '#6e6248';
    g.font = '500 32px "IBM Plex Mono", monospace';
    g.fillText(cat.minutes + ' MIN · ' + fmtMetres(cat.meters) + (cat.compass ? ' · ' + cat.compass : ''), 124, 104);
    var tex = new THREE.CanvasTexture(c);
    tex.needsUpdate = true;
    var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, sizeAttenuation: false }));
    sp.renderOrder = 5;
    sp.scale.set(0.19, 0.099, 1);
    return sp;
  }

  /* Merge many small geometries into one, baking each one's colour into a
     vertex-colour attribute. A dense city can be 1000+ footprints, and one
     mesh per building means one draw call per building; merged, the whole
     skyline draws in a single call and stays smooth while walking. */
  function mergeColored(THREE, entries) {
    var total = 0, i;
    var prepared = entries.map(function (entry) {
      var geo = entry.geo.index ? entry.geo.toNonIndexed() : entry.geo;
      if (!geo.attributes.normal) geo.computeVertexNormals();
      total += geo.attributes.position.count;
      return { geo: geo, color: entry.color };
    });

    var position = new Float32Array(total * 3);
    var normal = new Float32Array(total * 3);
    var color = new Float32Array(total * 3);
    var offset = 0;

    prepared.forEach(function (item) {
      var p = item.geo.attributes.position.array;
      var n = item.geo.attributes.normal.array;
      var count = item.geo.attributes.position.count;
      var c = item.color;
      for (i = 0; i < count; i++) {
        var to = (offset + i) * 3, from = i * 3;
        position[to] = p[from]; position[to + 1] = p[from + 1]; position[to + 2] = p[from + 2];
        normal[to] = n[from]; normal[to + 1] = n[from + 1]; normal[to + 2] = n[from + 2];
        color[to] = c.r; color[to + 1] = c.g; color[to + 2] = c.b;
      }
      offset += count;
      item.geo.dispose();
    });

    var merged = new THREE.BufferGeometry();
    merged.setAttribute('position', new THREE.BufferAttribute(position, 3));
    merged.setAttribute('normal', new THREE.BufferAttribute(normal, 3));
    merged.setAttribute('color', new THREE.BufferAttribute(color, 3));
    return merged;
  }

  function compassOf(bearing) {
    var names = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    return names[Math.round(((bearing % 360) + 360) % 360 / 45) % 8];
  }

  class WorldStage extends HTMLElement {
    static get observedAttributes() { return ['data', 'locname', 'buildings-url']; }

    connectedCallback() {
      if (this._booted) { this._resume(); return; }
      this._booted = true;
      this.style.display = 'block';
      this.style.width = '100%';
      this.style.height = '100%';
      this.style.position = 'relative';
      this._boot();
    }
    disconnectedCallback() { this._pause(); }
    _pause() { if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; } }
    _resume() {
      if (!this._renderer || this._raf) return;
      if (!this.contains(this._renderer.domElement)) this.appendChild(this._renderer.domElement);
      this._loop();
    }
    attributeChangedCallback() { if (this._scene) this._rebuildMarkers(); }

    _cats() {
      try { return JSON.parse(this.getAttribute('data') || '[]'); } catch (e) { return []; }
    }

    async _boot() {
      var THREE = await import(THREE_URL);
      this._THREE = THREE;
      if (!this.isConnected) return;

      var w = this.clientWidth || 900, h = this.clientHeight || 600;
      var renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h);
      renderer.domElement.style.display = 'block';
      this.appendChild(renderer.domElement);
      this._renderer = renderer;

      var scene = new THREE.Scene();
      scene.background = new THREE.Color(0xdcd2b4);
      scene.fog = new THREE.Fog(0xdcd2b4, 700, 2600);
      this._scene = scene;

      var camera = new THREE.PerspectiveCamera(52, w / h, 0.5, 9000);
      this._camera = camera;

      scene.add(new THREE.HemisphereLight(0xfff6e0, 0x8a8163, 1.05));
      var sun = new THREE.DirectionalLight(0xfff1d4, 0.75);
      sun.position.set(320, 620, 240);
      scene.add(sun);

      this._buildGround();
      this._buildProceduralCity();
      this._buildPlayer();
      this._rebuildMarkers();

      this._yaw = 0;
      this._keys = {};
      this._pos = new THREE.Vector3(0, 0, 0);
      var self = this;
      this._intro = document.hidden ? null : { el: 0, dur: 2.6 };
      this._onVis = function () { if (!document.hidden) self._resume(); };
      document.addEventListener('visibilitychange', this._onVis);

      this._bindInput();
      this._observeResize();
      this._loop();
      this._loadRealBuildings();
    }

    _buildGround() {
      var THREE = this._THREE, scene = this._scene;
      var ground = new THREE.Mesh(
        new THREE.PlaneGeometry(9000, 9000),
        new THREE.MeshLambertMaterial({ color: 0xc7bb98 })
      );
      ground.rotation.x = -Math.PI / 2;
      scene.add(ground);

      var plaza = new THREE.Mesh(new THREE.CircleGeometry(30, 40), new THREE.MeshLambertMaterial({ color: 0xd6c9a4 }));
      plaza.rotation.x = -Math.PI / 2;
      plaza.position.y = 0.12;
      scene.add(plaza);

      var ringMat = new THREE.MeshBasicMaterial({ color: 0x9c3b23, transparent: true, opacity: 0.5, side: THREE.DoubleSide });
      var ring = new THREE.Mesh(new THREE.RingGeometry(28.5, 30, 48), ringMat);
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.2;
      scene.add(ring);
    }

    /* Stand-in skyline, used until (or unless) real OSM footprints arrive. */
    _buildProceduralCity() {
      var THREE = this._THREE, scene = this._scene;
      var seed = hash(this.getAttribute('locname') || 'default');
      var r = rng(seed);
      var group = new THREE.Group();
      scene.add(group);
      this._proceduralCity = group;

      var CELL = 130, ROAD = 22, SPAN = 11;
      var reach = SPAN * CELL;
      var roadMat = new THREE.MeshLambertMaterial({ color: 0x8d8467 });
      for (var i = -SPAN; i <= SPAN; i++) {
        var rx = new THREE.Mesh(new THREE.PlaneGeometry(2 * reach, ROAD), roadMat);
        rx.rotation.x = -Math.PI / 2;
        rx.position.set(0, 0.05, i * CELL);
        group.add(rx);
        var rz = new THREE.Mesh(new THREE.PlaneGeometry(ROAD, 2 * reach), roadMat);
        rz.rotation.x = -Math.PI / 2;
        rz.position.set(i * CELL, 0.05, 0);
        group.add(rz);
      }

      var palette = [0xbfae8b, 0xa89a78, 0xcbbb96, 0xb0a184, 0xd0c19c].map(function (hex) {
        return new THREE.Color(hex);
      });
      var roofColor = new THREE.Color(0x8a7f62);
      var entries = [];
      for (var gx = -SPAN; gx < SPAN; gx++) {
        for (var gz = -SPAN; gz < SPAN; gz++) {
          var cx = gx * CELL + CELL / 2, cz = gz * CELL + CELL / 2;
          if (Math.hypot(cx, cz) < 60) continue;
          var n = 1 + Math.floor(r() * 3);
          for (var b = 0; b < n; b++) {
            var bw = 18 + r() * 34, bd = 18 + r() * 34;
            var bh = 9 + r() * (Math.hypot(cx, cz) < 420 ? 62 : 26);
            var ox = (r() - 0.5) * (CELL - ROAD - bw - 8);
            var oz = (r() - 0.5) * (CELL - ROAD - bd - 8);

            var body = new THREE.BoxGeometry(bw, bh, bd);
            body.translate(cx + ox, bh / 2, cz + oz);
            entries.push({ geo: body, color: palette[Math.floor(r() * palette.length)] });

            var roof = new THREE.BoxGeometry(bw + 2, 1.6, bd + 2);
            roof.translate(cx + ox, bh + 0.8, cz + oz);
            entries.push({ geo: roof, color: roofColor });
          }
        }
      }
      group.add(new THREE.Mesh(
        mergeColored(THREE, entries),
        new THREE.MeshLambertMaterial({ vertexColors: true })
      ));

      this._addTrees(group, r, 190, 60, reach * 0.9);
    }

    _addTrees(group, r, count, minRad, maxRad) {
      var THREE = this._THREE;
      var trunkColor = new THREE.Color(0x7a5f3e);
      var leafColor = new THREE.Color(0x5c7a42);
      var entries = [];
      for (var t = 0; t < count; t++) {
        var ang = r() * Math.PI * 2, rad = minRad + r() * (maxRad - minRad);
        var tx = Math.cos(ang) * rad, tz = Math.sin(ang) * rad;
        var trunk = new THREE.CylinderGeometry(0.32, 0.45, 4.4, 6);
        trunk.translate(tx, 2.2, tz);
        entries.push({ geo: trunk, color: trunkColor });
        var leaf = new THREE.SphereGeometry(2.4 + r() * 1.4, 8, 6);
        leaf.translate(tx, 6 + r(), tz);
        entries.push({ geo: leaf, color: leafColor });
      }
      group.add(new THREE.Mesh(
        mergeColored(THREE, entries),
        new THREE.MeshLambertMaterial({ vertexColors: true })
      ));
    }

    /* Real OpenStreetMap building footprints, extruded to their real height. */
    async _loadRealBuildings() {
      var url = this.getAttribute('buildings-url');
      if (!url) return;
      var payload;
      try {
        var response = await fetch(url);
        payload = await response.json();
      } catch (e) { return; }

      var buildings = (payload && payload.buildings) || [];
      if (!buildings.length || !this._scene) return;

      var THREE = this._THREE;
      var group = new THREE.Group();
      var palette = [0xbfae8b, 0xa89a78, 0xcbbb96, 0xb0a184, 0xd0c19c].map(function (hex) {
        return new THREE.Color(hex);
      });
      var seeded = rng(hash(this.getAttribute('locname') || 'osm'));
      var entries = [];

      buildings.forEach(function (b) {
        var pts = b.points || [];
        if (pts.length < 3) return;

        // OSM gives [east, north]. The shape is built in XY, then rotated flat
        // by -90 deg about X, which maps (x, y, z) -> (x, z, -y). Feeding in
        // (east, north) therefore lands at world (east, height, -north), so
        // north ends up at -z -- the same direction the bearing-placed markers
        // use, keeping buildings and markers on one compass.
        var shape = new THREE.Shape();
        shape.moveTo(pts[0][0], pts[0][1]);
        for (var i = 1; i < pts.length; i++) shape.lineTo(pts[i][0], pts[i][1]);
        shape.closePath();

        var height = Math.max(2.5, b.height || 9);
        var geo;
        try {
          geo = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
        } catch (e) {
          return;  // self-intersecting footprint -- skip rather than break the batch
        }
        geo.rotateX(-Math.PI / 2);
        entries.push({ geo: geo, color: palette[Math.floor(seeded() * palette.length)] });
      });

      if (!entries.length) return;
      group.add(new THREE.Mesh(
        mergeColored(THREE, entries),
        new THREE.MeshLambertMaterial({ vertexColors: true })
      ));

      this._addTrees(group, seeded, 70, 40, 420);

      // Real data wins: drop the stand-in city only once the real one is ready,
      // so the view never flashes empty ground.
      if (this._proceduralCity) {
        this._scene.remove(this._proceduralCity);
        this._proceduralCity = null;
      }
      this._scene.add(group);
      this._realCity = group;
      this.dispatchEvent(new CustomEvent('nhs-buildings-loaded', {
        bubbles: true, detail: { count: buildings.length }
      }));
    }

    _buildPlayer() {
      var THREE = this._THREE;
      var g = new THREE.Group();
      var skin = new THREE.MeshLambertMaterial({ color: 0xe8c9a0 });
      var cloth = new THREE.MeshLambertMaterial({ color: 0x1f3d2e });
      var legMat = new THREE.MeshLambertMaterial({ color: 0x33302a });

      // Roughly 1.8 m tall, so real building heights read correctly.
      var body = new THREE.Mesh(new THREE.CapsuleGeometry(0.28, 0.62, 6, 12), cloth);
      body.position.y = 1.05;
      g.add(body);
      var head = new THREE.Mesh(new THREE.SphereGeometry(0.25, 16, 12), skin);
      head.position.y = 1.62;
      g.add(head);
      this._legs = [];
      [-0.16, 0.16].forEach(function (x) {
        var leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.11, 0.46, 4, 8), legMat);
        leg.position.set(x, 0.4, 0);
        g.add(leg);
        this._legs.push(leg);
      }, this);
      [-0.36, 0.36].forEach(function (x) {
        var arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.09, 0.42, 4, 8), cloth);
        arm.position.set(x, 1.08, 0);
        g.add(arm);
      });

      // Oversized map pin so the walker stays findable among tall buildings.
      var pinMat = new THREE.MeshBasicMaterial({ color: 0x9c3b23, depthTest: false });
      var pin = new THREE.Mesh(new THREE.ConeGeometry(1.5, 3.4, 12), pinMat);
      pin.rotation.x = Math.PI;
      pin.position.y = 5.4;
      pin.renderOrder = 4;
      g.add(pin);
      var pinBall = new THREE.Mesh(new THREE.SphereGeometry(1.5, 14, 10), pinMat);
      pinBall.position.y = 8.1;
      pinBall.renderOrder = 4;
      g.add(pinBall);
      this._pin = pin;
      this._pinBall = pinBall;

      var shadow = new THREE.Mesh(
        new THREE.CircleGeometry(0.5, 20),
        new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.16 })
      );
      shadow.rotation.x = -Math.PI / 2;
      shadow.position.y = 0.25;
      g.add(shadow);

      this._scene.add(g);
      this._player = g;
    }

    _rebuildMarkers() {
      var THREE = this._THREE;
      if (!THREE || !this._scene) return;
      if (this._markerGroup) this._scene.remove(this._markerGroup);
      var group = new THREE.Group();
      this._scene.add(group);
      this._markerGroup = group;
      this._markers = [];
      this._labels = [];

      var cats = this._cats();
      var n = cats.length || 1;
      cats.forEach(function (cat, i) {
        var minutes = Math.max(1, cat.minutes || 1);
        var metres = cat.meters || minutes * WALK_M_PER_MIN;
        var dist = Math.max(25, metres);

        // A real geocoded place carries its true compass bearing (0 = north,
        // clockwise); everything else falls back to an even ring.
        var hasBearing = typeof cat.bearing === 'number';
        var x, z;
        if (hasBearing) {
          var rad = cat.bearing * Math.PI / 180;
          x = Math.sin(rad) * dist;
          z = -Math.cos(rad) * dist;
        } else {
          var ang = (i / n) * Math.PI * 2 + 0.52;
          x = Math.cos(ang) * dist;
          z = Math.sin(ang) * dist;
        }
        var col = new THREE.Color(cat.color || '#9c3b23');

        var pole = new THREE.Mesh(
          new THREE.CylinderGeometry(0.7, 0.7, MARKER_POLE_H, 10),
          new THREE.MeshLambertMaterial({ color: col })
        );
        pole.position.set(x, MARKER_POLE_H / 2, z);
        group.add(pole);

        var pad = new THREE.Mesh(
          new THREE.RingGeometry(5.6, 8, 30),
          new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.75, side: THREE.DoubleSide })
        );
        pad.rotation.x = -Math.PI / 2;
        pad.position.set(x, 0.3, z);
        group.add(pad);

        var beacon = new THREE.Mesh(
          new THREE.SphereGeometry(2, 14, 10),
          new THREE.MeshBasicMaterial({ color: col, depthTest: false })
        );
        beacon.position.set(x, MARKER_POLE_H + 1.4, z);
        beacon.renderOrder = 4;
        group.add(beacon);

        var sp = labelSprite(THREE, {
          letter: cat.letter, color: cat.color,
          short: cat.short || cat.label || '', name: cat.name || '',
          minutes: minutes, meters: metres,
          compass: hasBearing ? compassOf(cat.bearing) : ''
        });
        sp.position.set(x, LABEL_H, z);
        group.add(sp);
        this._labels.push(sp);

        var pathMat = new THREE.LineDashedMaterial({ color: col, dashSize: 9, gapSize: 7, transparent: true, opacity: 0.85 });
        var pathGeo = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(0, 0.4, 0), new THREE.Vector3(x, 0.4, z)
        ]);
        var line = new THREE.Line(pathGeo, pathMat);
        line.computeLineDistances();
        group.add(line);

        this._markers.push({ id: cat.id, x: x, z: z, beacon: beacon, phase: i });
      }, this);

      // Frame the camera around the furthest facility so all six markers are
      // on screen from the start, and grow the walker's pin to match, so it
      // stays findable when the view is pulled a kilometre back.
      var furthest = 0;
      this._markers.forEach(function (m) { furthest = Math.max(furthest, Math.hypot(m.x, m.z)); });
      // Markers sit all around the walker, so the camera looks down steeply
      // enough to cover every direction, not just the way it is facing.
      this._frame = Math.max(260, Math.min(2000, furthest * 1.45));
      this._camBack = this._frame * 0.78;
      this._camUp = this._frame * 1.08;
      // Haze has to start beyond the framed area, or pulling the camera back
      // to fit a distant facility fogs the whole neighborhood out.
      if (this._scene && this._scene.fog) {
        this._scene.fog.near = this._frame * 1.7;
        this._scene.fog.far = this._frame * 5.5;
      }
      if (this._player) this._player.scale.setScalar(1);
      if (this._pinScaleTargets) this._pinScaleTargets.forEach(function (p) { p.scale.setScalar(1); });
      var pinScale = Math.max(1, this._frame / 190);
      if (this._pin) this._pin.scale.setScalar(pinScale);
      if (this._pinBall) this._pinBall.scale.setScalar(pinScale);
      this._pinScaleTargets = [this._pin, this._pinBall];
      this._pinLift = pinScale;

      this._layoutLabels();
    }

    _layoutLabels() {
      if (!this._labels || !this._camera) return;
      var W = 0.19, IMG_RATIO = 150 / 512;
      var aspect = this._camera.aspect || 1.78;
      this._labels.forEach(function (sp) {
        sp.scale.set(W, W * IMG_RATIO * aspect, 1);
      });
    }

    _bindInput() {
      var self = this;
      this._onKeyDown = function (e) {
        var k = e.key.toLowerCase();
        if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].indexOf(k) >= 0) {
          self._keys[k] = true;
          e.preventDefault();
        }
      };
      this._onKeyUp = function (e) { self._keys[e.key.toLowerCase()] = false; };
      window.addEventListener('keydown', this._onKeyDown);
      window.addEventListener('keyup', this._onKeyUp);

      this._onDown = function (e) { self._drag = { x: e.clientX }; self.style.cursor = 'grabbing'; };
      this._onMove = function (e) {
        if (!self._drag) return;
        self._yaw -= (e.clientX - self._drag.x) * 0.006;
        self._drag = { x: e.clientX };
      };
      this._onUp = function () { self._drag = null; self.style.cursor = 'default'; };
      this.addEventListener('pointerdown', this._onDown);
      window.addEventListener('pointermove', this._onMove);
      window.addEventListener('pointerup', this._onUp);
    }

    _observeResize() {
      var self = this;
      this._ro = new ResizeObserver(function () {
        if (!self._renderer || !self._camera) return;
        var w = self.clientWidth || 1, h = self.clientHeight || 1;
        self._renderer.setSize(w, h);
        self._camera.aspect = w / h;
        self._camera.updateProjectionMatrix();
        self._layoutLabels();
      });
      this._ro.observe(this);
    }

    _loop() {
      var self = this, THREE = this._THREE;
      var back0 = this._camBack || 200, up0 = this._camUp || 165;
      if (!this._camPos) this._camPos = this._intro
        ? new THREE.Vector3(0, up0 * 4 + 900, back0 * 4 + 700)
        : new THREE.Vector3(0, up0, back0);
      if (!this._look) this._look = new THREE.Vector3(0, this._intro ? 0 : 14, 0);
      var camPos = this._camPos, look = this._look;
      var last = performance.now();
      var hudT = 0;

      (function frame(now) {
        if (!self._renderer) return;
        self._raf = requestAnimationFrame(frame);
        var dt = Math.min(0.05, (now - last) / 1000);
        last = now;

        var f = 0, sdir = 0;
        if (self._keys['w'] || self._keys['arrowup']) f += 1;
        if (self._keys['s'] || self._keys['arrowdown']) f -= 1;
        if (self._keys['a'] || self._keys['arrowleft']) sdir -= 1;
        if (self._keys['d'] || self._keys['arrowright']) sdir += 1;

        var moving = (f !== 0 || sdir !== 0);
        if (moving) {
          var len = Math.hypot(f, sdir) || 1;
          var speed = MOVE_SPEED * dt;
          var fx = -Math.sin(self._yaw) * (f / len) + Math.cos(self._yaw) * (sdir / len);
          var fz = -Math.cos(self._yaw) * (f / len) - Math.sin(self._yaw) * (sdir / len);
          self._pos.x += fx * speed;
          self._pos.z += fz * speed;
          self._pos.x = Math.max(-WORLD_LIMIT, Math.min(WORLD_LIMIT, self._pos.x));
          self._pos.z = Math.max(-WORLD_LIMIT, Math.min(WORLD_LIMIT, self._pos.z));
          self._player.rotation.y = Math.atan2(fx, fz);
        }
        self._player.position.set(self._pos.x, 0, self._pos.z);

        var t = now / 1000;
        if (self._legs) {
          var sw = moving ? Math.sin(t * 9) * 0.9 : 0;
          self._legs[0].rotation.x = sw;
          self._legs[1].rotation.x = -sw;
        }
        if (self._pin) {
          var lift = self._pinLift || 1;
          var bob = Math.sin(t * 2.2) * 0.6 * lift;
          self._pin.position.y = 5.4 * lift + bob;
          self._pinBall.position.y = 8.1 * lift + bob;
        }
        if (self._markers) {
          self._markers.forEach(function (m) {
            m.beacon.scale.setScalar(1 + Math.sin(t * 2.4 + m.phase) * 0.22);
          });
        }

        var back = self._camBack || 200, up = self._camUp || 165;
        var desired = new THREE.Vector3(
          self._pos.x + Math.sin(self._yaw) * back,
          up,
          self._pos.z + Math.cos(self._yaw) * back
        );
        var lookAt = new THREE.Vector3(self._pos.x, 14, self._pos.z);

        if (self._intro) {
          self._intro.el += dt;
          var k = Math.min(1, self._intro.el / self._intro.dur);
          var e = 1 - Math.pow(1 - k, 3);
          camPos.lerpVectors(new THREE.Vector3(0, up * 4 + 900, back * 4 + 700), desired, e);
          look.lerpVectors(new THREE.Vector3(0, 0, 0), lookAt, e);
          if (k >= 1) self._intro = null;
        } else {
          camPos.lerp(desired, 1 - Math.pow(0.001, dt));
          look.lerp(lookAt, 1 - Math.pow(0.001, dt));
        }
        self._camera.position.copy(camPos);
        self._camera.lookAt(look);

        hudT += dt;
        if (hudT > 0.12) { hudT = 0; self._updateHud(); }

        self._renderer.render(self._scene, self._camera);
      })(last);
    }

    _updateHud() {
      if (!this._markers) return;
      var px = this._pos.x, pz = this._pos.z;
      this._markers.forEach(function (m) {
        var metres = Math.hypot(m.x - px, m.z - pz);
        var mins = Math.max(1, Math.round(metres * DETOUR / WALK_M_PER_MIN));
        var dEl = document.querySelector('[data-nhs-dist="' + m.id + '"]');
        if (dEl) dEl.textContent = fmtMetres(metres);
        var tEl = document.querySelector('[data-nhs-live="' + m.id + '"]');
        if (tEl) tEl.textContent = mins + ' min';
      });
    }

    _dispose() {
      if (this._raf) cancelAnimationFrame(this._raf);
      if (this._ro) this._ro.disconnect();
      window.removeEventListener('keydown', this._onKeyDown);
      window.removeEventListener('keyup', this._onKeyUp);
      window.removeEventListener('pointermove', this._onMove);
      window.removeEventListener('pointerup', this._onUp);
      document.removeEventListener('visibilitychange', this._onVis);
      if (this._renderer) { this._renderer.dispose(); this._renderer = null; }
    }
  }

  customElements.define('world-stage', WorldStage);
})();
