(function () {
  if (customElements.get('globe-stage')) return;
  var THREE_URL = 'https://unpkg.com/three@0.184.0/build/three.module.js';
  var ATLAS_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json';

  function waitForGlobal(name, timeout) {
    return new Promise(function (resolve) {
      var t0 = Date.now();
      (function poll() {
        if (window[name]) return resolve(window[name]);
        if (Date.now() - t0 > (timeout || 9000)) return resolve(null);
        setTimeout(poll, 60);
      })();
    });
  }

  function lonLatToVec3(THREE, lon, lat, r) {
    var phi = (90 - lat) * Math.PI / 180;
    var theta = (lon + 180) * Math.PI / 180;
    return new THREE.Vector3(
      -r * Math.sin(phi) * Math.cos(theta),
      r * Math.cos(phi),
      r * Math.sin(phi) * Math.sin(theta)
    );
  }

  function ringsFromFeatures(features) {
    var polys = [];
    features.forEach(function (f) {
      var g = f.geometry;
      if (!g) return;
      var list = g.type === 'Polygon' ? [g.coordinates] : (g.type === 'MultiPolygon' ? g.coordinates : []);
      list.forEach(function (rings) {
        if (!rings || !rings[0] || rings[0].length < 4) return;
        var minX = 180, minY = 90, maxX = -180, maxY = -90;
        rings[0].forEach(function (p) {
          if (p[0] < minX) minX = p[0];
          if (p[0] > maxX) maxX = p[0];
          if (p[1] < minY) minY = p[1];
          if (p[1] > maxY) maxY = p[1];
        });
        polys.push({ rings: rings, bbox: [minX, minY, maxX, maxY] });
      });
    });
    return polys;
  }

  function inRing(x, y, ring) {
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
    }
    return inside;
  }

  function inPoly(x, y, poly) {
    var b = poly.bbox;
    if (x < b[0] || x > b[2] || y < b[1] || y > b[3]) return false;
    if (!inRing(x, y, poly.rings[0])) return false;
    for (var k = 1; k < poly.rings.length; k++) if (inRing(x, y, poly.rings[k])) return false;
    return true;
  }

  function dotTexture(THREE) {
    var c = document.createElement('canvas');
    c.width = c.height = 64;
    var g = c.getContext('2d');
    var rad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    rad.addColorStop(0, 'rgba(255,255,255,1)');
    rad.addColorStop(0.5, 'rgba(255,255,255,0.85)');
    rad.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = rad;
    g.beginPath();
    g.arc(32, 32, 32, 0, Math.PI * 2);
    g.fill();
    var t = new THREE.CanvasTexture(c);
    t.needsUpdate = true;
    return t;
  }

  var NODES = [
    { name: 'Copenhagen', lon: 12.57, lat: 55.68 },
    { name: 'Paris', lon: 2.35, lat: 48.86 },
    { name: 'Barcelona', lon: 2.17, lat: 41.39 },
    { name: 'Portland', lon: -122.68, lat: 45.52 },
    { name: 'Bogotá', lon: -74.07, lat: 4.71 },
    { name: 'Melbourne', lon: 144.96, lat: -37.81 },
    { name: 'Kuala Lumpur', lon: 101.69, lat: 3.14 },
    { name: 'Tokyo', lon: 139.69, lat: 35.69 }
  ];
  var ARCS = [[0, 1], [1, 2], [3, 4], [6, 7], [5, 6]];

  class GlobeStage extends HTMLElement {
    connectedCallback() {
      if (this._booted) { this._resume(); return; }
      this._booted = true;
      this.style.display = 'block';
      this.style.width = '100%';
      this.style.height = '100%';
      this.style.position = 'relative';
      this.style.cursor = 'grab';
      this._boot();
    }

    disconnectedCallback() { this._pause(); }
    _pause() { if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; } }
    _resume() {
      if (!this._renderer || this._raf) return;
      if (!this.contains(this._renderer.domElement)) this.appendChild(this._renderer.domElement);
      this._renderLoop();
    }

    async _boot() {
      var THREE = await import(THREE_URL);
      this._THREE = THREE;
      if (!this.isConnected) return;

      var w = this.clientWidth || 900;
      var h = this.clientHeight || 600;

      var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h);
      renderer.domElement.style.display = 'block';
      this.appendChild(renderer.domElement);
      this._renderer = renderer;

      var scene = new THREE.Scene();
      scene.background = new THREE.Color(0x11201a);
      this._scene = scene;

      var camera = new THREE.PerspectiveCamera(38, w / h, 0.01, 100);
      camera.position.set(0, 0, 3.35);
      camera.lookAt(0, 0, 0);
      this._camera = camera;

      var world = new THREE.Group();
      scene.add(world);
      this._world = world;
      world.rotation.x = 0.22;
      world.position.set(0, 0, 0);
      this._homeX = 0;
      this._homeY = 0;

      var R = 1;

      var ocean = new THREE.Mesh(
        new THREE.SphereGeometry(R * 0.995, 64, 48),
        new THREE.MeshBasicMaterial({ color: 0x18382a })
      );
      world.add(ocean);

      var glow = new THREE.Mesh(
        new THREE.SphereGeometry(R * 1.14, 48, 32),
        new THREE.MeshBasicMaterial({ color: 0x3f7a5c, transparent: true, opacity: 0.11, side: THREE.BackSide })
      );
      world.add(glow);

      var gratMat = new THREE.LineBasicMaterial({ color: 0x4d8a68, transparent: true, opacity: 0.45 });
      var gratPts = [];
      for (var lat = -60; lat <= 60; lat += 30) {
        for (var lon = -180; lon < 180; lon += 4) {
          gratPts.push(lonLatToVec3(THREE, lon, lat, R * 1.001), lonLatToVec3(THREE, lon + 4, lat, R * 1.001));
        }
      }
      for (var lo = -180; lo < 180; lo += 30) {
        for (var la = -88; la < 88; la += 4) {
          gratPts.push(lonLatToVec3(THREE, lo, la, R * 1.001), lonLatToVec3(THREE, lo, la + 4, R * 1.001));
        }
      }
      var gratGeo = new THREE.BufferGeometry().setFromPoints(gratPts);
      world.add(new THREE.LineSegments(gratGeo, gratMat));

      this._bindInput();
      this._renderLoop();
      this._observeResize();

      var topo = await waitForGlobal('topojson', 9000);
      if (!this.isConnected) return;
      if (topo) {
        try {
          var res = await fetch(ATLAS_URL);
          var atlas = await res.json();
          var fc = topo.feature(atlas, atlas.objects.countries);
          this._addGeography(fc.features, R);
        } catch (e) { /* graticule-only fallback */ }
      }
      this._addNodes(R);
      this.dispatchEvent(new CustomEvent('globe-ready', { bubbles: true }));
    }

    _addGeography(features, R) {
      var THREE = this._THREE;
      var polys = ringsFromFeatures(features);

      var coastPts = [];
      polys.forEach(function (p) {
        p.rings.forEach(function (ring) {
          for (var i = 0; i < ring.length - 1; i++) {
            coastPts.push(lonLatToVec3(THREE, ring[i][0], ring[i][1], R * 1.004));
            coastPts.push(lonLatToVec3(THREE, ring[i + 1][0], ring[i + 1][1], R * 1.004));
          }
        });
      });
      var coast = new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints(coastPts),
        new THREE.LineBasicMaterial({ color: 0xe9dcbc, transparent: true, opacity: 0.92 })
      );
      this._world.add(coast);

      var landPts = [];
      for (var lat = -84; lat <= 84; lat += 1.4) {
        var cos = Math.cos(lat * Math.PI / 180);
        var step = Math.min(6, 1.4 / Math.max(cos, 0.12));
        for (var lon = -180; lon < 180; lon += step) {
          for (var i = 0; i < polys.length; i++) {
            if (inPoly(lon, lat, polys[i])) {
              landPts.push(lonLatToVec3(THREE, lon, lat, R * 1.002));
              break;
            }
          }
        }
      }
      var pts = new THREE.Points(
        new THREE.BufferGeometry().setFromPoints(landPts),
        new THREE.PointsMaterial({
          color: 0xcdb98a, size: 0.016, map: dotTexture(THREE),
          transparent: true, alphaTest: 0.15, sizeAttenuation: true, depthWrite: false
        })
      );
      this._world.add(pts);
    }

    _addNodes(R) {
      var THREE = this._THREE;
      var group = new THREE.Group();
      this._world.add(group);
      this._nodeGroup = group;

      var nodeGeo = new THREE.SphereGeometry(0.014, 12, 10);
      var nodeMat = new THREE.MeshBasicMaterial({ color: 0xd1552f });
      var ringMat = new THREE.MeshBasicMaterial({ color: 0xd1552f, transparent: true, opacity: 0.55, side: THREE.DoubleSide });
      this._pulses = [];

      NODES.forEach(function (n, i) {
        var p = lonLatToVec3(THREE, n.lon, n.lat, R * 1.012);
        var m = new THREE.Mesh(nodeGeo, nodeMat);
        m.position.copy(p);
        group.add(m);

        var ring = new THREE.Mesh(new THREE.RingGeometry(0.02, 0.026, 24), ringMat.clone());
        ring.position.copy(p);
        ring.lookAt(p.clone().multiplyScalar(2));
        group.add(ring);
        this._pulses.push({ mesh: ring, phase: i * 0.7 });
      }, this);

      var arcMat = new THREE.LineBasicMaterial({ color: 0xd1552f, transparent: true, opacity: 0.4 });
      ARCS.forEach(function (pair) {
        var a = lonLatToVec3(THREE, NODES[pair[0]].lon, NODES[pair[0]].lat, R * 1.01);
        var b = lonLatToVec3(THREE, NODES[pair[1]].lon, NODES[pair[1]].lat, R * 1.01);
        var mid = a.clone().add(b).multiplyScalar(0.5).normalize().multiplyScalar(R * (1.1 + a.distanceTo(b) * 0.12));
        var curve = new THREE.QuadraticBezierCurve3(a, mid, b);
        group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(48)), arcMat));
      });
    }

    _bindInput() {
      var self = this;
      this._drag = null;
      this._spin = 0.0016;
      this._vel = 0;

      this._onDown = function (e) {
        self._drag = { x: e.clientX, y: e.clientY };
        self.style.cursor = 'grabbing';
      };
      this._onMove = function (e) {
        if (!self._drag || !self._world) return;
        var dx = e.clientX - self._drag.x;
        var dy = e.clientY - self._drag.y;
        self._world.rotation.y += dx * 0.005;
        self._world.rotation.x = Math.max(-0.9, Math.min(0.9, self._world.rotation.x + dy * 0.003));
        self._vel = dx * 0.0006;
        self._drag = { x: e.clientX, y: e.clientY };
      };
      this._onUp = function () { self._drag = null; self.style.cursor = 'grab'; };

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
      });
      this._ro.observe(this);
    }

    _renderLoop() {
      var self = this;
      var t0 = performance.now();
      (function frame(now) {
        if (!self._renderer) return;
        self._raf = requestAnimationFrame(frame);
        var t = (now - t0) / 1000;

        if (!self._drag && self._world && !self._zooming) {
          self._world.rotation.y += self._spin + self._vel;
          self._vel *= 0.94;
        }
        if (self._pulses) {
          self._pulses.forEach(function (p) {
            var k = (Math.sin(t * 1.6 + p.phase) + 1) / 2;
            p.mesh.scale.setScalar(1 + k * 1.5);
            p.mesh.material.opacity = 0.55 * (1 - k);
          });
        }
        if (self._zooming) self._stepZoom(now);
        self._renderer.render(self._scene, self._camera);
      })(t0);
    }

    zoomIn() {
      if (this._zooming || !this._camera) return;
      this._zooming = { t0: performance.now(), dur: 2100, z0: this._camera.position.z, fov0: this._camera.fov };
    }

    _stepZoom(now) {
      var z = this._zooming;
      var k = Math.min(1, (now - z.t0) / z.dur);
      var e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      this._world.position.set(this._homeX * (1 - e), this._homeY * (1 - e), 0);
      this._camera.position.set(0, 0, z.z0 + (0.55 - z.z0) * e);
      this._camera.lookAt(0, 0, 0);
      this._camera.fov = z.fov0 + e * 44;
      this._camera.updateProjectionMatrix();
      this._world.rotation.y += 0.004 + e * 0.022;
      if (k >= 1) {
        this._zooming = null;
        this.dispatchEvent(new CustomEvent('globe-entered', { bubbles: true }));
        document.dispatchEvent(new CustomEvent('nhs-globe-entered'));
      }
    }

    _dispose() {
      if (this._raf) cancelAnimationFrame(this._raf);
      if (this._ro) this._ro.disconnect();
      window.removeEventListener('pointermove', this._onMove);
      window.removeEventListener('pointerup', this._onUp);
      if (this._renderer) { this._renderer.dispose(); this._renderer = null; }
    }
  }

  customElements.define('globe-stage', GlobeStage);
})();
