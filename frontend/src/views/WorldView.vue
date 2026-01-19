<template>
  <div class="app-container">
    <h2>Dengue Viewer</h2>

    <!-- SLIDER + FLECHAS -->
    <div class="slider-container">
      <button
        class="arrow-btn"
        @click="prevWeek"
        :disabled="selectedWeekIndex <= 0"
      >
        ◀
      </button>

      <input
        type="range"
        v-model="selectedWeekIndex"
        :min="0"
        :max="weeks.length - 1"
        @input="loadWeekData"
      />

      <button
        class="arrow-btn"
        @click="nextWeek"
        :disabled="selectedWeekIndex >= weeks.length - 1"
      >
        ▶
      </button>

      <span class="week-label">
        {{ weeks[selectedWeekIndex] }}
      </span>

      <!-- SELECTOR DE MÉTRICA -->
      <label class="metric-label">
        Métrica:
        <select v-model="metric">
          <option value="cases">Casos nuevos</option>
          <option value="incidence">Incidencia</option>
          <option value="density">Casos / km²</option>
        </select>
      </label>
    </div>

    <!-- CONTROLES DE PAÍSES -->
    <div class="country-controls">
      <label class="country-filter-label">
        Filtrar país:
        <input
          v-model="countryFilter"
          type="text"
          placeholder="Escribe parte del nombre..."
        />
      </label>

      <div class="country-checkboxes">
        <label
          v-for="c in displayedCountries"
          :key="c"
          class="country-item"
        >
          <input
            type="checkbox"
            v-model="visibleCountries"
            :value="c"
          />
          {{ c }}
        </label>
      </div>
    </div>

    <!-- MAPA -->
    <div id="map" class="map"></div>
  </div>
</template>

<script setup>
import { onMounted, ref, computed, watch } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import axios from "axios";

const map = ref(null);
const layerGroup = ref(null);
const legendControl = ref(null);

const weeks = ref([]);
const selectedWeekIndex = ref(0);

// gestión de países
const allCountries = ref([]);       // lista total de países conocidos
const visibleCountries = ref([]);   // países actualmente visibles (checkbox)
const countryFilter = ref("");      // filtro de texto

// métrica seleccionada
const metric = ref("cases"); // "cases" | "incidence" | "density"

// cortes fijos por métrica (ajústalos a tu gusto)
const BREAKS = {
  cases:      [0, 10, 50, 100, 500, 1000, Infinity],
  incidence:  [0, 1, 5, 10, 25, 50, Infinity],
  density:    [0, 0.1, 0.5, 1, 2, 5, Infinity],
};

// colores (de amarillo a rojo oscuro)
// tiene que haber (breaks.length - 1) colores
const COLORS = [
  "#ffffb2",
  "#fed976",
  "#feb24c",
  "#fd8d3c",
  "#f03b20",
  "#bd0026",
];

// etiquetas para la leyenda
const METRIC_LABEL = {
  cases: "Casos nuevos",
  incidence: "Incidencia (casos / 100.000 hab.)",
  density: "Casos por km²",
};

// países que se muestran en la lista de checkboxes
const displayedCountries = computed(() => {
  const q = countryFilter.value.toLowerCase();
  return allCountries.value
    .filter((c) => c.toLowerCase().includes(q))
    .sort();
});

// valor a usar según la métrica
function valueForMetric(record) {
  if (metric.value === "incidence") {
    return record.incidence ?? 0;
  }
  if (metric.value === "density") {
    return record.density ?? 0;
  }
  // por defecto, casos nuevos
  return record.cases ?? 0;
}

// color según el valor + métrica (usa BREAKS + COLORS)
function getColorForMetric(value) {
  const breaks = BREAKS[metric.value] || BREAKS.cases;
  const colors = COLORS;

  // suponemos colors.length === breaks.length - 1
  for (let i = breaks.length - 2; i >= 0; i--) {
    if (value >= breaks[i]) {
      return colors[i];
    }
  }
  return colors[0];
}

// actualizar contenido de la leyenda
function updateLegend() {
  if (!legendControl.value) return;

  const div = legendControl.value.getContainer();
  if (!div) return;

  const breaks = BREAKS[metric.value] || BREAKS.cases;
  const colors = COLORS;
  const title = METRIC_LABEL[metric.value] || "Valor";

  let html = `<div><strong>${title}</strong></div>`;

  // para cada intervalo
  for (let i = 0; i < breaks.length - 1; i++) {
    const from = breaks[i];
    const to = breaks[i + 1];

    let rangeLabel;
    if (!isFinite(to)) {
      rangeLabel = `≥ ${from}`;
    } else if (from === 0) {
      rangeLabel = `0 – ${to}`;
    } else {
      rangeLabel = `${from} – ${to}`;
    }

    html += `
      <div>
        <i style="background:${colors[i]}"></i>
        <span>${rangeLabel}</span>
      </div>
    `;
  }

  div.innerHTML = html;
}

async function loadWeekData() {
  if (!weeks.value.length) return;

  const week = weeks.value[selectedWeekIndex.value];



  const API_URL = import.meta.env.VITE_API_BASE_URL;

  const res = await axios.get(`${API_URL}/api/cases/${week}`);

  const records = res.data.data || [];

  layerGroup.value.clearLayers();

  // actualizar listado global de países (NO se resetea visibleCountries,
  // así el filtro permanece entre semanas)
  records.forEach((r) => {
    if (!allCountries.value.includes(r.country)) {
      allCountries.value.push(r.country);
      // por defecto, país nuevo -> visible
      visibleCountries.value.push(r.country);
    }
  });

  // aplicar filtro por países visibles (checkbox)
  const activeRecords = records.filter((r) =>
    visibleCountries.value.includes(r.country)
  );

  if (!activeRecords.length) return;

  activeRecords.forEach((r) => {
    const v = valueForMetric(r);
    const color = getColorForMetric(v);

    L.geoJSON(r.geometry, {
      style: {
        color: "#660000",
        weight: 1,
        fillColor: color,
        fillOpacity: 0.8,
      },
    })
      .bindPopup(
        `
        <b>${r.country}</b><br>
        Casos: ${r.cases ?? 0}<br>
        Incidencia: ${r.incidence ?? 0}<br>
        Casos / km²: ${
          r.density?.toFixed ? r.density.toFixed(3) : r.density ?? 0
        }
      `
      )
      .addTo(layerGroup.value);
  });

  // actualizar leyenda (por si cambia la métrica)
  updateLegend();
}

// flechas de navegación
function prevWeek() {
  if (selectedWeekIndex.value > 0) {
    selectedWeekIndex.value -= 1;
    loadWeekData();
  }
}

function nextWeek() {
  if (selectedWeekIndex.value < weeks.value.length - 1) {
    selectedWeekIndex.value += 1;
    loadWeekData();
  }
}

onMounted(async () => {
  map.value = L.map("map").setView([0, -60], 3);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
  }).addTo(map.value);

  layerGroup.value = L.layerGroup().addTo(map.value);

  // leyenda Leaflet
  legendControl.value = L.control({ position: "bottomright" });
  legendControl.value.onAdd = function () {
    const div = L.DomUtil.create("div", "info legend");
    return div;
  };
  legendControl.value.addTo(map.value);

  // cargar lista de semanas
  const API_URL = import.meta.env.VITE_API_BASE_URL;

  const r = await axios.get(`${API_URL}/api/weeks`);
  weeks.value = r.data;

  await loadWeekData();
});

// cuando cambian los checkboxes, repintar el mapa (misma semana)
watch(
  visibleCountries,
  () => {
    loadWeekData();
  },
  { deep: true }
);

// cuando cambia la métrica, repintar el mapa + actualizar leyenda
watch(metric, () => {
  loadWeekData();
  updateLegend();
});
</script>

<style>
.app-container {
  width: 100%;
  padding: 10px;
}

.slider-container {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.arrow-btn {
  padding: 3px 8px;
  font-size: 16px;
  cursor: pointer;
}

.arrow-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.week-label {
  margin-left: 10px;
  font-weight: bold;
  min-width: 90px;
}

.metric-label {
  margin-left: 20px;
}

/* CONTROLES DE PAÍSES */
.country-controls {
  display: flex;
  gap: 20px;
  margin-bottom: 10px;
  align-items: flex-start;
}

.country-filter-label input {
  margin-left: 5px;
  padding: 2px 4px;
}

.country-checkboxes {
  max-height: 150px;
  overflow-y: auto;
  border: 1px solid #ccc;
  padding: 4px 8px;
  min-width: 250px;
  background: #fafafa;
}

.country-item {
  display: block;
  font-size: 12px;
  margin-bottom: 2px;
}

/* MAPA */
.map {
  width: 100%;
  height: 80vh;
  border: 2px solid #ccc;
}

/* LEYENDA */
.info.legend {
  background: white;
  padding: 6px 8px;
  font: 12px/14px Arial, Helvetica, sans-serif;
  box-shadow: 0 0 15px rgba(0, 0, 0, 0.2);
  border-radius: 5px;
}

.info.legend div {
  margin-bottom: 4px;
}

.info.legend i {
  width: 18px;
  height: 18px;
  float: left;
  margin-right: 6px;
  opacity: 0.8;
}

.info.legend span {
  vertical-align: middle;
}
</style>
