(function () {
  if (customElements.get('world-stage')) return;
  var THREE_URL = 'https://unpkg.com/three@0.184.0/build/three.module.js';
  var M_PER_UNIT = 8;
  var WALK_M_PER_MIN = 80;

  function rng(seed) {
    var s = seed >>> 0 || 1;
    return function () { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  }
  function hash(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
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
    g.fillText(cat.short.toUpperCase(), 124, 52);
    g.fillStyle = '#6e6248';
    g.font = '500 34px "IBM Plex Mono", monospace';
    g.fillText(cat.minutes + ' MIN · ' + cat.meters + ' M', 124, 104);
    var tex = new THREE.CanvasTexture(c);
    tex.needsUpdate = true;
    var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, sizeAttenuation: false }));
    sp.renderOrder = 5;
    sp.scale.set(0.19, 0.099, 1);
    return sp;
  }

  class WorldStage extends HTMLElement {
    static get observedAttributes() { return ['data', 'locname']; }

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
      scene.fog = new THREE.Fog(0xdcd2b4, 420, 1700);
      this._scene = scene;

      var camera = new THREE.PerspectiveCamera(52, w / h, 0.5, 4000);
      this._camera = camera;

      scene.add(new THREE.HemisphereLight(0xfff6e0, 0x8a8163, 1.05));
      var sun = new THREE.DirectionalLight(0xfff1d4, 0.75);
      sun.position.set(120, 220, 90);
      scene.add(sun);

      this._buildCity();
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
    }

    _buildCity() {
      var THREE = this._THREE, scene = this._scene;
      var seed = hash(this.getAttribute('locname') || 'default');
      var r = rng(seed);

      var ground = new THREE.Mesh(
        new THREE.PlaneGeometry(2600, 2600),
        new THREE.MeshLambertMaterial({ color: 0xc7bb98 })
      );
      ground.rotation.x = -Math.PI / 2;
      scene.add(ground);

      var CELL = 46, ROAD = 10, SPAN = 8;
      var roadMat = new THREE.MeshLambertMaterial({ color: 0x8d8467 });
      for (var i = -SPAN; i <= SPAN; i++) {
        var rx = new THREE.Mesh(new THREE.PlaneGeometry(2600, ROAD), roadMat);
        rx.rotation.x = -Math.PI / 2;
        rx.position.set(0, 0.05, i * CELL);
        scene.add(rx);
        var rz = new THREE.Mesh(new THREE.PlaneGeometry(ROAD, 2600), roadMat);
        rz.rotation.x = -Math.PI / 2;
        rz.position.set(i * CELL, 0.05, 0);
        scene.add(rz);
      }

      var centreMat = new THREE.MeshBasicMaterial({ color: 0xe3d9bb });
      for (var j = -SPAN; j <= SPAN; j++) {
        for (var s = -28; s <= 28; s += 2) {
          var dashA = new THREE.Mesh(new THREE.PlaneGeometry(6, 0.7), centreMat);
          dashA.rotation.x = -Math.PI / 2;
          dashA.position.set(s * CELL / 2.2, 0.09, j * CELL);
          scene.add(dashA);
        }
      }

      var palette = [0xbfae8b, 0xa89a78, 0xcbbb96, 0xb0a184, 0xd0c19c];
      var roofMat = new THREE.MeshLambertMaterial({ color: 0x8a7f62 });

      for (var gx = -SPAN; gx < SPAN; gx++) {
        for (var gz = -SPAN; gz < SPAN; gz++) {
          var cx = gx * CELL + CELL / 2, cz = gz * CELL + CELL / 2;
          if (Math.hypot(cx, cz) < 34) continue;
          var n = 1 + Math.floor(r() * 3);
          for (var b = 0; b < n; b++) {
            var bw = 8 + r() * 14, bd = 8 + r() * 14;
            var bh = 6 + r() * (Math.hypot(cx, cz) < 160 ? 30 : 14);
            var ox = (r() - 0.5) * (CELL - ROAD - bw - 4);
            var oz = (r() - 0.5) * (CELL - ROAD - bd - 4);
            var col = palette[Math.floor(r() * palette.length)];
            var m = new THREE.Mesh(
              new THREE.BoxGeometry(bw, bh, bd),
              new THREE.MeshLambertMaterial({ color: col })
            );
            m.position.set(cx + ox, bh / 2, cz + oz);
            scene.add(m);
            var roof = new THREE.Mesh(new THREE.BoxGeometry(bw + 1.2, 1, bd + 1.2), roofMat);
            roof.position.set(cx + ox, bh + 0.5, cz + oz);
            scene.add(roof);
          }
        }
      }

      var trunkMat = new THREE.MeshLambertMaterial({ color: 0x7a5f3e });
      var leafMat = new THREE.MeshLambertMaterial({ color: 0x5c7a42 });
      for (var t = 0; t < 130; t++) {
        var ang = r() * Math.PI * 2, rad = 24 + r() * 300;
        var tx = Math.cos(ang) * rad, tz = Math.sin(ang) * rad;
        var trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.7, 5, 6), trunkMat);
        trunk.position.set(tx, 2.5, tz);
        scene.add(trunk);
        var leaf = new THREE.Mesh(new THREE.SphereGeometry(3 + r() * 1.6, 8, 6), leafMat);
        leaf.position.set(tx, 7 + r(), tz);
        scene.add(leaf);
      }

      var plaza = new THREE.Mesh(new THREE.CircleGeometry(22, 40), new THREE.MeshLambertMaterial({ color: 0xd6c9a4 }));
      plaza.rotation.x = -Math.PI / 2;
      plaza.position.y = 0.12;
      scene.add(plaza);

      var ringMat = new THREE.MeshBasicMaterial({ color: 0x9c3b23, transparent: true, opacity: 0.5, side: THREE.DoubleSide });
      var ring = new THREE.Mesh(new THREE.RingGeometry(21, 22.4, 48), ringMat);
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.2;
      scene.add(ring);
    }

    _buildPlayer() {
      var THREE = this._THREE;
      var g = new THREE.Group();
      var skin = new THREE.MeshLambertMaterial({ color: 0xe8c9a0 });
      var cloth = new THREE.MeshLambertMaterial({ color: 0x1f3d2e });
      var legMat = new THREE.MeshLambertMaterial({ color: 0x33302a });

      var body = new THREE.Mesh(new THREE.CapsuleGeometry(1.5, 3.2, 6, 12), cloth);
      body.position.y = 5.4;
      g.add(body);
      var head = new THREE.Mesh(new THREE.SphereGeometry(1.35, 16, 12), skin);
      head.position.y = 8.4;
      g.add(head);
      this._legs = [];
      [-0.85, 0.85].forEach(function (x) {
        var leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.6, 2.4, 4, 8), legMat);
        leg.position.set(x, 2.1, 0);
        g.add(leg);
        this._legs.push(leg);
      }, this);
      [-1.9, 1.9].forEach(function (x) {
        var arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.5, 2.2, 4, 8), cloth);
        arm.position.set(x, 5.6, 0);
        g.add(arm);
      });

      var pinMat = new THREE.MeshBasicMaterial({ color: 0x9c3b23 });
      var pin = new THREE.Mesh(new THREE.ConeGeometry(1.5, 3.4, 12), pinMat);
      pin.rotation.x = Math.PI;
      pin.position.y = 12.4;
      g.add(pin);
      var pinBall = new THREE.Mesh(new THREE.SphereGeometry(1.5, 14, 10), pinMat);
      pinBall.position.y = 15.1;
      g.add(pinBall);
      this._pin = pin;
      this._pinBall = pinBall;

      var shadow = new THREE.Mesh(
        new THREE.CircleGeometry(2.6, 20),
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
        var dist = Math.max(12, minutes * 10);
        var ang = (i / n) * Math.PI * 2 + 0.52;
        var x = Math.cos(ang) * dist, z = Math.sin(ang) * dist;
        var col = new THREE.Color(cat.color || '#9c3b23');

        var pole = new THREE.Mesh(
          new THREE.CylinderGeometry(0.55, 0.55, 26, 10),
          new THREE.MeshLambertMaterial({ color: col })
        );
        pole.position.set(x, 13, z);
        group.add(pole);

        var pad = new THREE.Mesh(
          new THREE.RingGeometry(4.4, 6.2, 30),
          new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.75, side: THREE.DoubleSide })
        );
        pad.rotation.x = -Math.PI / 2;
        pad.position.set(x, 0.3, z);
        group.add(pad);

        var beacon = new THREE.Mesh(new THREE.SphereGeometry(1.6, 14, 10), new THREE.MeshBasicMaterial({ color: col }));
        beacon.position.set(x, 26.6, z);
        group.add(beacon);

        var sp = labelSprite(THREE, {
          letter: cat.letter, color: cat.color, short: cat.short || cat.label || '',
          minutes: minutes, meters: Math.round(dist * M_PER_UNIT / 10) * 10
        });
        sp.position.set(x, 31, z);
        group.add(sp);
        this._labels.push(sp);

        var pathMat = new THREE.LineDashedMaterial({ color: col, dashSize: 4, gapSize: 3.4, transparent: true, opacity: 0.85 });
        var pathGeo = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(0, 0.4, 0), new THREE.Vector3(x, 0.4, z)
        ]);
        var line = new THREE.Line(pathGeo, pathMat);
        line.computeLineDistances();
        group.add(line);

        this._markers.push({ id: cat.id, x: x, z: z, beacon: beacon, phase: i });
      }, this);
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
      if (!this._camPos) this._camPos = this._intro
        ? new THREE.Vector3(0, 860, 680)
        : new THREE.Vector3(0, 182, 210);
      if (!this._look) this._look = new THREE.Vector3(0, this._intro ? 0 : 12, 0);
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
          var speed = 34 * dt;
          var fx = -Math.sin(self._yaw) * (f / len) + Math.cos(self._yaw) * (sdir / len);
          var fz = -Math.cos(self._yaw) * (f / len) - Math.sin(self._yaw) * (sdir / len);
          self._pos.x += fx * speed;
          self._pos.z += fz * speed;
          self._pos.x = Math.max(-340, Math.min(340, self._pos.x));
          self._pos.z = Math.max(-340, Math.min(340, self._pos.z));
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
          var bob = Math.sin(t * 2.2) * 0.6;
          self._pin.position.y = 12.4 + bob;
          self._pinBall.position.y = 15.1 + bob;
        }
        if (self._markers) {
          self._markers.forEach(function (m) {
            m.beacon.scale.setScalar(1 + Math.sin(t * 2.4 + m.phase) * 0.22);
          });
        }

        var desired = new THREE.Vector3(
          self._pos.x + Math.sin(self._yaw) * 210,
          182,
          self._pos.z + Math.cos(self._yaw) * 210
        );
        var lookAt = new THREE.Vector3(self._pos.x, 12, self._pos.z);

        if (self._intro) {
          self._intro.el += dt;
          var k = Math.min(1, self._intro.el / self._intro.dur);
          var e = 1 - Math.pow(1 - k, 3);
          camPos.lerpVectors(new THREE.Vector3(0, 860, 680), desired, e);
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
        var units = Math.hypot(m.x - px, m.z - pz);
        var metres = Math.round(units * M_PER_UNIT / 10) * 10;
        var mins = Math.max(1, Math.round(metres / WALK_M_PER_MIN));
        var dEl = document.querySelector('[data-nhs-dist="' + m.id + '"]');
        if (dEl) dEl.textContent = metres >= 1000 ? (metres / 1000).toFixed(1) + ' km' : metres + ' m';
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
