<template>
  <div class="thai-view-container">
    <div class="header">
      <h2>🇹🇭 Monitor Dengue Bangkok 2025</h2>
      <div class="controls">
        <button @click="prevWeek" :disabled="weekIndex <= 0">◀</button>
        <span class="week-display">{{ currentWeekLabel }}</span>
        <button @click="nextWeek" :disabled="weekIndex >= weeks.length - 1">▶</button>
      </div>
    </div>

    <div class="stats-bar" v-if="currentData.length">
      <div class="stat-item">
        <strong>Total Casos (Semana):</strong> {{ totalWeeklyCases }}
      </div>
      <div class="stat-item">
        <strong>Distrito más afectado:</strong> {{ topDistrict.name }} ({{ topDistrict.cases }})
      </div>
    </div>

    <div id="thai-map" class="map-container"></div>
    
    <div class="legend-floating">
      <h4>Casos Nuevos</h4>
      <div v-for="(color, i) in colors" :key="i" class="legend-item">
        <span class="color-box" :style="{ background: color }"></span>
        <span>{{ breaks[i] }} - {{ breaks[i+1] || '+' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import axios from 'axios';

const map = ref(null);
const geoLayer = ref(null);
const weeks = ref([]);
const weekIndex = ref(0);
const currentData = ref([]);

// Configuración de Colores (Amarillo -> Rojo Oscuro)
const colors = ['#FFEDA0', '#FEB24C', '#FD8D3C', '#FC4E2A', '#E31A1C', '#BD0026', '#800026'];
const breaks = [1, 5, 10, 20, 30, 50, 100];

const currentWeekLabel = computed(() => weeks.value[weekIndex.value] || 'Cargando...');

const totalWeeklyCases = computed(() => 
  currentData.value.reduce((sum, d) => sum + d.cases, 0)
);

const topDistrict = computed(() => {
  if (!currentData.value.length) return { name: '-', cases: 0 };
  const top = [...currentData.value].sort((a, b) => b.cases - a.cases)[0];
  return { name: top.district, cases: top.cases };
});

// Función para obtener color
function getColor(d) {
  // Si es 0, null o undefined, devuelve BLANCO
  if (!d || d === 0) {
    return '#ffffff'; 
  }

  for (let i = breaks.length - 1; i >= 0; i--) {
    if (d >= breaks[i]) return colors[i];
  }
  
  return '#ffffff'; // Fallback por seguridad
}

// Cargar Semanas
onMounted(async () => {
  // Inicializar Mapa
  map.value = L.map('thai-map').setView([13.7563, 100.5018], 10); // Centrado en Bangkok
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap contributors & CARTO'
  }).addTo(map.value);
  
  geoLayer.value = L.geoJSON(null, {
    style: styleFeature,
    onEachFeature: onEachFeature
  }).addTo(map.value);

  // Obtener lista de semanas del backend
  try {
    const API_URL = import.meta.env.VITE_API_BASE_URL;

    const res = await axios.get(`${API_URL}/api/thailand/weeks`);



    weeks.value = res.data;
    if (weeks.value.length > 0) loadWeekData();
  } catch (e) {
    console.error("Error cargando semanas:", e);
  }
});

// Cargar Datos de la Semana
async function loadWeekData() {
  const week = weeks.value[weekIndex.value];
  try {
    const API_URL = import.meta.env.VITE_API_BASE_URL;

    const res = await axios.get(`${API_URL}/api/thailand/cases/${week}`);

    currentData.value = res.data.data;
    updateMap();
  } catch (e) {
    console.error("Error datos semana:", e);
  }
}

function updateMap() {
  if (!geoLayer.value) return;
  geoLayer.value.clearLayers();
  
  // Transformar datos planos a GeoJSON
  const features = currentData.value.map(d => ({
    type: "Feature",
    properties: {
      name: d.district,
      cases: d.cases,
      density: d.density
    },
    geometry: d.geometry
  }));

  geoLayer.value.addData({ type: "FeatureCollection", features: features });
}

function styleFeature(feature) {
  return {
    fillColor: getColor(feature.properties.cases),
    weight: 1,
    opacity: 1,
    color: 'white',
    dashArray: '3',
    fillOpacity: 0.7
  };
}

function onEachFeature(feature, layer) {
  layer.bindPopup(`
    <div style="text-align:center">
      <strong>${feature.properties.name}</strong><br/>
      ${feature.properties.cases} Casos<br/>
      <small>Densidad: ${feature.properties.density.toFixed(2)}</small>
    </div>
  `);
}

function nextWeek() { if(weekIndex.value < weeks.value.length - 1) { weekIndex.value++; loadWeekData(); } }
function prevWeek() { if(weekIndex.value > 0) { weekIndex.value--; loadWeekData(); } }

</script>

<style scoped>
.thai-view-container { display: flex; flex-direction: column; height: 100vh; font-family: sans-serif; }
.header { padding: 1rem; background: #f8f9fa; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #ddd; }
.controls button { padding: 5px 15px; font-size: 1.2rem; cursor: pointer; }
.week-display { margin: 0 15px; font-weight: bold; font-size: 1.1rem; }
.stats-bar { display: flex; gap: 20px; padding: 10px 20px; background: #e9ecef; font-size: 0.9rem; }
.map-container { flex: 1; width: 100%; z-index: 1; }

.legend-floating {
  position: absolute; bottom: 30px; right: 30px; z-index: 1000;
  background: white; padding: 10px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.2);
}
.legend-item { display: flex; align-items: center; margin-top: 4px; font-size: 12px; }
.color-box { width: 15px; height: 15px; margin-right: 8px; border: 1px solid #ccc; }
</style>