function changeSummarizationStyle(event) {
  // get the form element
  const form = document.getElementById("summarization-style-form");

  // get the data
  const formData = new FormData(form);

  // get the "filter" field from the form data
  const filter = formData.get("filter");

  // the URL we are currently is of the form:
  // /foo/bar/previous-filter/
  // so we want to replace the "previous-filter" part with the new filter
  const currentPathname = window.location.pathname;
  const newPathname = currentPathname.replace(/\/[^\/]*\/$/, `/${filter}/`);

  // go to it!
  window.location.pathname = newPathname;
}


function doNothing(event) {
  event.preventDefault();
  event.stopPropagation();
}


function showSummarizationStyleForm() {
  // get the form element
  const form = document.getElementById("summarization-style-form");

  // remove the 'hidden' class from the form
  form.classList.remove("hidden");
}


function listenForKeyboardEvents(event) {
  // check to see if the user pressed Option+Shift+S
  if (event.altKey && event.shiftKey && event.code === "KeyS") {
    showSummarizationStyleForm();
  }
}


// ---- Council vote maps --------------------------------------------------------
//
// Interactive MapLibre GL choropleth — one per Council Bill.
// Districts 1-7 colored by vote; hover to see member name + vote.
// At-large members (Pos. 8-9) rendered as HTML badges above the map.
//
// Color key: green = In Favor, red = No/Against/Opposed, gray = Absent/Excused.

var DISTRICT_GEOJSON_URL =
  "https://raw.githubusercontent.com/seattleio/seattle-boundaries-data/master/data/city-council-districts.geojson";
var MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
var VOTE_COLORS = { yes: "#16a34a", no: "#dc2626", absent: "#9ca3af", unknown: "#e5e7eb", unavailable: "#111827" };
var DISTRICT_MEMBERS = {
  1: "Rob Saka",
  2: "Eddie Lin",
  3: "Joy Hollingsworth",
  4: "Maritza Rivera",
  5: "Debora Juarez",
  6: "Dan Strauss",
  7: "Robert Kettle",
};

function voteColor(v) {
  if (!v) return VOTE_COLORS.unknown;
  if (v.in_favor) return VOTE_COLORS.yes;
  if (v.opposed)  return VOTE_COLORS.no;
  if (v.absent)   return VOTE_COLORS.absent;
  return VOTE_COLORS.unknown;
}

function buildColorExpr(byDistrict) {
  var expr = ["match", ["get", "district"]];
  for (var d = 1; d <= 7; d++) expr.push(d, voteColor(byDistrict[d]));
  expr.push(VOTE_COLORS.unknown);
  return expr;
}

function computeBounds(geojson) {
  var w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  geojson.features.forEach(function (f) {
    var rings = f.geometry.type === "MultiPolygon"
      ? f.geometry.coordinates.reduce(function (a, p) { return a.concat(p[0]); }, [])
      : f.geometry.coordinates[0];
    rings.forEach(function (c) {
      if (c[0] < w) w = c[0]; if (c[1] < s) s = c[1];
      if (c[0] > e) e = c[0]; if (c[1] > n) n = c[1];
    });
  });
  return [[w, s], [e, n]];
}

function enrichGeoJSON(geojson, byDistrict, amendments) {
  // Build sponsor lookup: lastName → amendment short title
  var amendmentsByLastName = {};
  // Build vote lookup: full member name (lowercase) → vote row
  var amendmentVotesByName = {};
  (amendments || []).forEach(function (a) {
    (a.action_by || "").split(/,\s*/).forEach(function (name) {
      var parts = name.trim().split(/\s+/);
      var lastName = parts[parts.length - 1].toLowerCase();
      if (lastName) amendmentsByLastName[lastName] = a.action;
    });
    (a.votes || []).forEach(function (v) {
      if (v.name) amendmentVotesByName[v.name.toLowerCase()] = v;
    });
  });

  return {
    type: "FeatureCollection",
    features: geojson.features.map(function (f) {
      var d = f.properties.district;
      var v = byDistrict[d];
      var vtype = v ? (v.in_favor ? "yes" : v.opposed ? "no" : v.absent ? "absent" : "unknown") : "unknown";
      var memberName = (v && v.name) ? v.name : (DISTRICT_MEMBERS[d] || "");
      var memberLastName = memberName.split(/\s+/).pop().toLowerCase();
      var amendmentText = amendmentsByLastName[memberLastName] || "";
      var av = amendmentVotesByName[memberName.toLowerCase()] || null;
      return Object.assign({}, f, {
        id: d,
        properties: Object.assign({}, f.properties, {
          member_name: v ? v.name : "",
          vote_text: v ? v.vote : "",
          vote_type: vtype,
          amendment_text: amendmentText,
          amendment_vote_text: av ? av.vote : "",
          amendment_vote_type: av ? (av.in_favor ? "yes" : av.opposed ? "no" : "absent") : "",
        }),
      });
    }),
  };
}

function initBillMap(canvas, baseGeoJSON) {
  var votes;
  try { votes = JSON.parse(canvas.dataset.votes || "[]"); } catch (e) { return; }

  var voteStatus = canvas.dataset.voteStatus || "pending";
  var pendingLabel = canvas.dataset.pendingLabel || "";
  var hasVotes = votes.length > 0;
  var isUnknown = voteStatus === "unknown";
  var byDistrict = {};
  if (hasVotes) {
    votes.forEach(function (v) { if (typeof v.district === "number") byDistrict[v.district] = v; });
  }

  var amendments;
  try { amendments = JSON.parse(canvas.dataset.amendments || "[]"); } catch (e) { amendments = []; }

  var geojson = enrichGeoJSON(baseGeoJSON, byDistrict, amendments);
  var bounds  = computeBounds(geojson);

  var map = new maplibregl.Map({
    container: canvas,
    style: MAP_STYLE,
    bounds: bounds,
    fitBoundsOptions: { padding: 24, animate: false },
    attributionControl: false,
    scrollZoom: false,
    boxZoom: false,
    dragRotate: false,
    dragPan: false,
    keyboard: false,
    doubleClickZoom: false,
    touchZoomRotate: false,
  });

  var popup = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    className: "vote-popup",
    offset: 8,
  });
  var hoveredId = null;

  map.on("load", function () {
    map.addSource("districts", { type: "geojson", data: geojson, generateId: false });

    // Colored district fills (all grey when no votes)
    map.addLayer({
      id: "district-fills",
      type: "fill",
      source: "districts",
      paint: {
        "fill-color": hasVotes ? buildColorExpr(byDistrict) : isUnknown ? VOTE_COLORS.unavailable : VOTE_COLORS.unknown,
        "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.85, 0.60],
      },
    });

    // Hover darkening overlay
    map.addLayer({
      id: "district-hover",
      type: "fill",
      source: "districts",
      paint: {
        "fill-color": "#000",
        "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.12, 0],
      },
    });

    // District outlines
    map.addLayer({
      id: "district-outlines",
      type: "line",
      source: "districts",
      paint: { "line-color": "#fff", "line-width": 1.5 },
    });

    // District number labels
    map.addLayer({
      id: "district-labels",
      type: "symbol",
      source: "districts",
      layout: {
        "text-field": ["get", "district"],
        "text-size": 11,
        "text-font": ["Noto Sans Regular"],
        "text-anchor": "center",
      },
      paint: { "text-color": "#1f2937", "text-halo-color": "#fff", "text-halo-width": 1.5 },
    });

    if (hasVotes) {
      // Hover: highlight district + show popup with member name/vote
      map.on("mousemove", "district-fills", function (ev) {
        map.getCanvas().style.cursor = "pointer";
        if (hoveredId !== null) {
          map.setFeatureState({ source: "districts", id: hoveredId }, { hover: false });
        }
        hoveredId = ev.features[0].id;
        map.setFeatureState({ source: "districts", id: hoveredId }, { hover: true });

        var p = ev.features[0].properties;
        var cls = p.vote_type === "yes" ? "vp-yes" : p.vote_type === "no" ? "vp-no" : "vp-absent";
        var avCls = p.amendment_vote_type === "yes" ? "vp-yes" : p.amendment_vote_type === "no" ? "vp-no" : "vp-absent";
        popup.setLngLat(ev.lngLat).setHTML(
          '<div class="vp-district">District ' + p.district + "</div>" +
          (p.member_name
            ? '<div class="vp-name">'  + p.member_name + "</div>" +
              '<div class="vp-vote ' + cls + '">' + (p.vote_text || "Unknown") + "</div>" +
              (p.amendment_vote_text ? '<div class="vp-amendment-vote ' + avCls + '">Amendment: ' + p.amendment_vote_text + "</div>" : "") +
              (p.amendment_text ? '<div class="vp-amendment">Sponsored: ' + p.amendment_text + "</div>" : "")
            : '<div class="vp-vote vp-absent">No data</div>')
        ).addTo(map);
      });

      map.on("mouseleave", "district-fills", function () {
        map.getCanvas().style.cursor = "";
        if (hoveredId !== null) {
          map.setFeatureState({ source: "districts", id: hoveredId }, { hover: false });
        }
        hoveredId = null;
        popup.remove();
      });
    } else {
      // No vote data — either "unknown" (passed, no records) or "pending" (not yet voted)
      map.on("mousemove", "district-fills", function (ev) {
        map.getCanvas().style.cursor = "pointer";
        if (hoveredId !== null) {
          map.setFeatureState({ source: "districts", id: hoveredId }, { hover: false });
        }
        hoveredId = ev.features[0].id;
        map.setFeatureState({ source: "districts", id: hoveredId }, { hover: true });

        var p = ev.features[0].properties;
        var memberName = DISTRICT_MEMBERS[p.district] || "";
        var avCls2 = p.amendment_vote_type === "yes" ? "vp-yes" : p.amendment_vote_type === "no" ? "vp-no" : "vp-absent";
        var voteLabel = isUnknown
          ? '<div class="vp-vote vp-vote-unknown">Voting status unknown</div>'
          : '<div class="vp-vote vp-upcoming">' + (pendingLabel || "Vote upcoming") + '</div>';
        popup.setLngLat(ev.lngLat).setHTML(
          '<div class="vp-district">District ' + p.district + "</div>" +
          (memberName ? '<div class="vp-name">' + memberName + "</div>" : "") +
          voteLabel +
          (p.amendment_vote_text ? '<div class="vp-amendment-vote ' + avCls2 + '">Amendment: ' + p.amendment_vote_text + "</div>" : "") +
          (p.amendment_text ? '<div class="vp-amendment">Sponsored: ' + p.amendment_text + "</div>" : "")
        ).addTo(map);
      });

      map.on("mouseleave", "district-fills", function () {
        map.getCanvas().style.cursor = "";
        if (hoveredId !== null) {
          map.setFeatureState({ source: "districts", id: hoveredId }, { hover: false });
        }
        hoveredId = null;
        popup.remove();
      });

      // Bottom label
      var overlay = document.createElement("div");
      overlay.className = "bill-map-pending-overlay";
      var label = document.createElement("div");
      label.className = "bill-map-pending-text";
      label.textContent = isUnknown
        ? "Vote data unavailable \u2014 individual member votes were not recorded"
        : (pendingLabel || "Voting upcoming");
      overlay.appendChild(label);
      canvas.appendChild(overlay);
    }
  });
}

// ---- District population-density maps -----------------------------------
//
// A second choropleth per bill, next to the vote map: districts colored by
// how prevalent one of the bill's flagged "Legally Recognized Populations"
// is in that district (Census/ACS data, see district_demographics.py).
// Sequential purple scale — deliberately distinct from the vote map's
// categorical red/green/gray so the two are never confused at a glance.

var DENSITY_SCALE = ["#f3e8ff", "#d8b4fe", "#a855f7", "#7e22ce", "#581c87"];

function densityBreaks(values) {
  var min = Math.min.apply(null, values);
  var max = Math.max.apply(null, values);
  if (min === max) { max = min + 1; }
  var step = (max - min) / DENSITY_SCALE.length;
  var breaks = [];
  for (var i = 0; i <= DENSITY_SCALE.length; i++) breaks.push(min + step * i);
  return breaks;
}

function densityColorFor(value, breaks) {
  for (var i = 0; i < DENSITY_SCALE.length; i++) {
    if (value <= breaks[i + 1] || i === DENSITY_SCALE.length - 1) return DENSITY_SCALE[i];
  }
  return DENSITY_SCALE[DENSITY_SCALE.length - 1];
}

function buildDensityColorExpr(byDistrict, breaks) {
  var expr = ["match", ["get", "district"]];
  for (var d = 1; d <= 7; d++) {
    var v = byDistrict[d];
    expr.push(d, typeof v === "number" ? densityColorFor(v, breaks) : "#e5e7eb");
  }
  expr.push("#e5e7eb");
  return expr;
}

function renderDensityLegend(container, population, breaks) {
  container.innerHTML = "";
  var title = document.createElement("div");
  title.className = "density-legend-title";
  title.textContent = population.label + (population.note ? " *" : "");
  container.appendChild(title);

  var citywide = document.createElement("div");
  citywide.className = "density-legend-citywide";
  citywide.textContent = "Citywide: " + population.citywide_percent.toFixed(1) + "% of " + (population.unit || "population");
  container.appendChild(citywide);

  var row = document.createElement("div");
  row.className = "density-legend-row";
  for (var i = 0; i < DENSITY_SCALE.length; i++) {
    var item = document.createElement("span");
    item.className = "density-legend-item";
    var swatch = document.createElement("span");
    swatch.className = "density-legend-swatch";
    swatch.style.background = DENSITY_SCALE[i];
    var label = document.createElement("span");
    label.textContent = breaks[i].toFixed(1) + "–" + breaks[i + 1].toFixed(1) + "%";
    item.appendChild(swatch);
    item.appendChild(label);
    row.appendChild(item);
  }
  container.appendChild(row);

  if (population.note) {
    var note = document.createElement("div");
    note.className = "density-legend-note";
    note.textContent = "* " + population.note;
    container.appendChild(note);
  }
}

function renderDensityTabs(container, populations, activeIndex, onSelect) {
  container.innerHTML = "";
  if (populations.length < 2) return;
  populations.forEach(function (p, i) {
    var tab = document.createElement("button");
    tab.type = "button";
    tab.className = "density-tab" + (i === activeIndex ? " density-tab-active" : "");
    tab.textContent = p.label;
    tab.addEventListener("click", function () { onSelect(i); });
    container.appendChild(tab);
  });
}

function initDensityMap(canvas, baseGeoJSON) {
  var populations;
  try { populations = JSON.parse(canvas.dataset.populations || "[]"); } catch (e) { return; }
  if (!populations.length) return;

  var wrapper = canvas.closest(".bill-density-map");
  var tabsEl = wrapper ? wrapper.querySelector(".density-tabs") : null;
  var legendEl = wrapper ? wrapper.querySelector(".bill-density-legend") : null;

  var bounds = computeBounds(baseGeoJSON);
  var geojson = {
    type: "FeatureCollection",
    features: baseGeoJSON.features.map(function (f) {
      return Object.assign({}, f, { id: f.properties.district });
    }),
  };

  var map = new maplibregl.Map({
    container: canvas,
    style: MAP_STYLE,
    bounds: bounds,
    fitBoundsOptions: { padding: 24, animate: false },
    attributionControl: false,
    scrollZoom: false,
    boxZoom: false,
    dragRotate: false,
    dragPan: false,
    keyboard: false,
    doubleClickZoom: false,
    touchZoomRotate: false,
  });

  var popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: "vote-popup", offset: 8 });
  var hoveredId = null;
  var activeIndex = 0;

  function currentBreaks() {
    var byDistrict = populations[activeIndex].by_district;
    return densityBreaks([1, 2, 3, 4, 5, 6, 7].map(function (d) { return byDistrict[d]; }));
  }

  function applyActivePopulation() {
    var population = populations[activeIndex];
    var breaks = currentBreaks();
    if (map.getLayer("density-fills")) {
      map.setPaintProperty("density-fills", "fill-color", buildDensityColorExpr(population.by_district, breaks));
    }
    if (legendEl) renderDensityLegend(legendEl, population, breaks);
    if (tabsEl) renderDensityTabs(tabsEl, populations, activeIndex, function (i) { activeIndex = i; applyActivePopulation(); });
  }

  map.on("load", function () {
    map.addSource("density-districts", { type: "geojson", data: geojson, generateId: false });

    map.addLayer({
      id: "density-fills",
      type: "fill",
      source: "density-districts",
      paint: {
        "fill-color": "#e5e7eb",
        "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.9, 0.75],
      },
    });
    map.addLayer({
      id: "density-hover",
      type: "fill",
      source: "density-districts",
      paint: { "fill-color": "#000", "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.12, 0] },
    });
    map.addLayer({
      id: "density-outlines",
      type: "line",
      source: "density-districts",
      paint: { "line-color": "#fff", "line-width": 1.5 },
    });
    map.addLayer({
      id: "density-labels",
      type: "symbol",
      source: "density-districts",
      layout: { "text-field": ["get", "district"], "text-size": 11, "text-font": ["Noto Sans Regular"], "text-anchor": "center" },
      paint: { "text-color": "#1f2937", "text-halo-color": "#fff", "text-halo-width": 1.5 },
    });

    applyActivePopulation();

    map.on("mousemove", "density-fills", function (ev) {
      map.getCanvas().style.cursor = "pointer";
      if (hoveredId !== null) map.setFeatureState({ source: "density-districts", id: hoveredId }, { hover: false });
      hoveredId = ev.features[0].id;
      map.setFeatureState({ source: "density-districts", id: hoveredId }, { hover: true });

      var d = ev.features[0].properties.district;
      var population = populations[activeIndex];
      var value = population.by_district[d];
      popup.setLngLat(ev.lngLat).setHTML(
        '<div class="vp-district">District ' + d + "</div>" +
        '<div class="vp-name">' + population.label + "</div>" +
        '<div class="vp-vote dp-value">' + (typeof value === "number" ? value.toFixed(1) + "% of " + (population.unit || "population") : "No data") + "</div>"
      ).addTo(map);
    });
    map.on("mouseleave", "density-fills", function () {
      map.getCanvas().style.cursor = "";
      if (hoveredId !== null) map.setFeatureState({ source: "density-districts", id: hoveredId }, { hover: false });
      hoveredId = null;
      popup.remove();
    });
  });
}

function initAllBillMaps() {
  if (typeof maplibregl === "undefined") return;
  var voteCanvases = document.querySelectorAll(".bill-map-canvas[data-votes]");
  var densityCanvases = document.querySelectorAll(".bill-density-canvas[data-populations]");
  if (!voteCanvases.length && !densityCanvases.length) return;
  fetch(DISTRICT_GEOJSON_URL)
    .then(function (r) { return r.json(); })
    .then(function (geojson) {
      // Lazily initialize each map only when it scrolls near the viewport.
      // This avoids exhausting the browser's WebGL context limit (~8-16 per page)
      // which would cause the first-initialized maps to lose their context.
      // Two maps per bill now share this same limit, so it's worth revisiting
      // if pages with many labeled bills start losing map contexts.
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          observer.unobserve(entry.target);
          if (entry.target.classList.contains("bill-density-canvas")) {
            initDensityMap(entry.target, geojson);
          } else {
            initBillMap(entry.target, geojson);
          }
        });
      }, { rootMargin: "300px" });
      voteCanvases.forEach(function (c) { observer.observe(c); });
      densityCanvases.forEach(function (c) { observer.observe(c); });
    })
    .catch(function (err) { console.warn("Could not load Seattle district GeoJSON:", err); });
}

document.addEventListener("DOMContentLoaded", initAllBillMaps);


// Intro panel chevron: smooth-scroll to the bills section on click.
document.addEventListener("DOMContentLoaded", function () {
  var chevron = document.getElementById("intro-chevron");
  if (chevron) {
    chevron.addEventListener("click", function () {
      var target = document.getElementById("main-content");
      if (target) {
        target.scrollIntoView({ behavior: "smooth" });
      }
    });
  }
});


// ---- "View By Who is Impacted" stakeholder filter -------------------------
//
// Client-side filter over the bills already rendered on the page (no
// server round-trip). "__none__" matches bills with no stakes at all
// (unlabeled, or labeled with an empty "Who's affected" list).
//
// Each filter state is reflected in a ?affects= query param, so a filtered
// view is a URL someone can copy and share — reloading it (or opening it
// fresh) restores the same filter. Browser back/forward moves between
// filter states too, via pushState + popstate.

var STAKEHOLDER_FILTER_PARAM = "affects";

function initStakeholderFilter() {
  var select = document.getElementById("stakeholder-filter");
  if (!select) return;

  var entries = document.querySelectorAll(".bill-entry[data-stakeholder-groups]");
  var breadcrumb = document.getElementById("stakeholder-filter-breadcrumb");
  var breadcrumbLabel = document.getElementById("stakeholder-filter-breadcrumb-label");
  var clearBtn = document.getElementById("stakeholder-filter-clear");
  var emptyMsg = document.getElementById("stakeholder-filter-empty");

  function applyFilter() {
    var value = select.value;
    var visibleCount = 0;

    entries.forEach(function (entry) {
      var groups = entry.dataset.stakeholderGroups
        ? entry.dataset.stakeholderGroups.split("|")
        : [];
      var show =
        value === "" ||
        (value === "__none__" ? groups.length === 0 : groups.indexOf(value) !== -1);
      // .bill-entry is an <article>, and site.css's HTML5-reset rule sets
      // "article { display: block }" — an author rule, which beats the
      // browser's default "[hidden] { display: none }" user-agent rule
      // regardless of selector specificity. So the hidden *attribute*
      // wouldn't actually hide it; set the inline style directly instead.
      entry.style.display = show ? "" : "none";
      if (show) visibleCount++;
    });

    if (value === "") {
      breadcrumb.hidden = true;
    } else {
      breadcrumb.hidden = false;
      breadcrumbLabel.textContent = select.options[select.selectedIndex].textContent;
    }

    emptyMsg.hidden = !(value !== "" && visibleCount === 0);
  }

  function pushUrlForValue(value) {
    var url = new URL(window.location.href);
    if (value) {
      url.searchParams.set(STAKEHOLDER_FILTER_PARAM, value);
    } else {
      url.searchParams.delete(STAKEHOLDER_FILTER_PARAM);
    }
    if (url.href !== window.location.href) {
      history.pushState({ stakeholderFilter: value }, "", url);
    }
  }

  // Restore filter state from the URL on load, if it names a real option
  // (an unrecognized value — a stale link, a typo — falls back to "All Bills"
  // rather than leaving the dropdown on a phantom selection).
  var initialValue = new URLSearchParams(window.location.search).get(
    STAKEHOLDER_FILTER_PARAM
  );
  if (initialValue && select.querySelector('option[value="' + CSS.escape(initialValue) + '"]')) {
    select.value = initialValue;
  }
  applyFilter();

  select.addEventListener("change", function () {
    pushUrlForValue(select.value);
    applyFilter();
  });

  clearBtn.addEventListener("click", function () {
    select.value = "";
    pushUrlForValue("");
    applyFilter();
    select.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  window.addEventListener("popstate", function () {
    var value = new URLSearchParams(window.location.search).get(STAKEHOLDER_FILTER_PARAM) || "";
    select.value = select.querySelector('option[value="' + CSS.escape(value) + '"]') ? value : "";
    applyFilter();
  });
}

document.addEventListener("DOMContentLoaded", initStakeholderFilter);


async function shareBill(btn) {
  const article = btn.closest("article.bill-entry[id]");
  if (!article) return;
  const url = window.location.origin + window.location.pathname + "#" + article.id;
  const confirm = btn.querySelector(".share-btn-confirm");
  const label = btn.querySelector(".share-btn-label");

  // Use native Web Share API on supported devices (mobile)
  if (navigator.share) {
    try {
      await navigator.share({ url });
      return;
    } catch (e) {
      if (e.name === "AbortError") return; // user cancelled
    }
  }

  // Fallback: copy to clipboard
  try {
    await navigator.clipboard.writeText(url);
  } catch (e) {
    // Last resort: execCommand
    const ta = document.createElement("textarea");
    ta.value = url;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }

  // Show "Copied!" confirmation
  label.style.display = "none";
  confirm.textContent = "Copied!";
  setTimeout(() => {
    confirm.textContent = "";
    label.style.display = "";
  }, 2000);
}


// When the document is ready, make sure the summarization style is selected
// correctly, and set up the event handler for when it changes. Use basic
// javascript; no jQuery.
document.addEventListener("DOMContentLoaded", function () {
  // get the current filter from the URL. It will be the final path component
  // of the URL, so split the URL on "/" and get the last element
  const splits = window.location.pathname.split("/");
  let filter = splits[splits.length - 2];

  // make sure it is one of the valid filters, which are:
  // `concise` <-- that's it, for the moment!
  if (!["concise"].includes(filter)) {
    // if it is not one of the valid filters, default to `concise`
    filter = "concise";
  }

  // get the form element
  const form = document.getElementById("summarization-style-form");

  // select the correct option under the "filter" select element
  form.elements["filter"].value = filter;

  // set up the event handler for when the form is submitted
  form.addEventListener("submit", doNothing);

  // set up the event handler for when the form is changed
  form.addEventListener("change", changeSummarizationStyle);

  // set up a listener for keyboard up events
  document.addEventListener("keydown", listenForKeyboardEvents);
});

