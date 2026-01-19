<template>
  <div class="layout-container">
    
    <div class="sidebar">
      <h2>🇧🇷 Monitor Dengue</h2>
      
      <div v-if="loadingWeeks" class="loading-text">Cargando fechas...</div>
      
      <div v-else class="controls-box">
        <div class="selectors">
          <div class="form-group">
            <label>Año:</label>
            <select v-model="selectedYear" @change="updateSliderFromDropdown">
              <option v-for="y in uniqueYears" :key="y" :value="y">{{ y }}</option>
            </select>
          </div>
          
          <div class="form-group">
            <label>Semana:</label>
            <select v-model="selectedWeekOnly" @change="updateSliderFromDropdown">
              <option v-for="w in weeksInSelectedYear" :key="w" :value="w">{{ w }}</option>
            </select>
          </div>
        </div>

        <div class="slider-container">
          
          <div class="slider-row">
            
            <button 
              class="nav-btn" 
              @click="prevWeek" 
              :disabled="sliderIndex <= 0"
              title="Semana anterior"
            >
              ◀
            </button>

            <input 
              type="range" 
              min="0" 
              :max="allWeeks.length - 1" 
              v-model="sliderIndex" 
              @input="onSliderChange"
              class="slider"
            >

            <button 
              class="nav-btn" 
              @click="nextWeek" 
              :disabled="sliderIndex >= allWeeks.length - 1"
              title="Siguiente semana"
            >
              ▶
            </button>
            
          </div>

          <div class="slider-label">
            {{ currentWeekLabel }}
          </div>
        </div>
      </div>

      <div class="legend-box">
        <h4>Casos Semanales</h4>
        <div class="gradient-bar"></div>
        <div class="labels">
          <span>0</span>
          <span>50+</span>
          <span>500+</span>
        </div>
      </div>

      <div class="table-container">
        <h3>Municipios con Casos ({{ tableData.length }})</h3>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Municipio</th>
                <th>Casos</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in tableData" :key="row.id" @click="zoomToMunicipality(row.bounds)">
                <td>{{ row.name }}</td>
                <td class="cases-cell">{{ row.cases }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="tableData.length === 0" class="no-data">
            No hay casos registrados esta semana.
          </div>
        </div>
      </div>
    </div>

    <div class="map-area">
      <div id="map-brazil" class="map-frame"></div>
      <div v-if="loadingMap" class="map-loader">
        <div class="spinner"></div> Cargando mapa...
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, onUnmounted } from 'vue';
import axios from 'axios';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// --- ESTADO ---
const weeks = ref([]); 
const selectedWeekIndex = ref(0);
const loading = ref(false);
const error = ref(null);
const isPlaying = ref(false);
let playInterval = null;

// --- CACHÉ (LA CLAVE PARA LA VELOCIDAD) ---
const dataCache = new Map();

let map = null;
let geoJsonLayer = null;

// --- CORRECCIÓN: URL SIN AWAIT ---
const API_URL = import.meta.env.VITE_API_BASE_URL;
const API_BASE = `${API_URL}/api`; 

// --- COMPUTADAS ---
const currentWeek = computed(() => {
  if (weeks.value.length === 0) return '';
  return weeks.value[selectedWeekIndex.value];
});

// --- CICLO DE VIDA ---
onMounted(async () => {
  initMap();
  await loadWeeks();
});

onUnmounted(() => {
  stopPlay();
});

// --- FUNCIONES ---

const initMap = () => {
  // Coordenadas centradas en Brasil
  map = L.map('map').setView([-14.2350, -51.9253], 4); 
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19
  }).addTo(map);
};

const loadWeeks = async () => {
  try {
    loading.value = true;
    const res = await axios.get(`${API_BASE}/brasil/weeks`);
    weeks.value = res.data;
    
    if (weeks.value.length > 0) {
      selectedWeekIndex.value = weeks.value.length - 1;
    }
  } catch (e) {
    error.value = "Error cargando semanas: " + e.message;
  } finally {
    loading.value = false;
  }
};

const loadWeekData = async () => {
  const week = currentWeek.value;
  if (!week) return;

  // 1. REVISAR CACHÉ (Velocidad instantánea si ya se visitó)
  if (dataCache.has(week)) {
    updateMapLayer(dataCache.get(week));
    return;
  }

  try {
    if (!isPlaying.value) loading.value = true;

    // Nota: Asegúrate que tu endpoint de Brasil acepte el parámetro "?week="
    const res = await axios.get(`${API_BASE}/brasil`, {
      params: { week: week }
    });
    
    const data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
    
    // 2. GUARDAR EN CACHÉ
    dataCache.set(week, data);
    
    updateMapLayer(data);
  } catch (e) {
    console.error("Error geojson:", e);
  } finally {
    loading.value = false;
  }
};

const updateMapLayer = (data) => {
  if (geoJsonLayer) {
    geoJsonLayer.clearLayers();
    map.removeLayer(geoJsonLayer);
  }
  geoJsonLayer = L.geoJSON(data, {
    style: styleFeature,
    onEachFeature: onEachFeature
  }).addTo(map);
};

// --- CONTROLES Y WATCHERS ---

const prevWeek = () => {
  if (selectedWeekIndex.value > 0) selectedWeekIndex.value--;
};

const nextWeek = () => {
  if (selectedWeekIndex.value < weeks.value.length - 1) selectedWeekIndex.value++;
};

const togglePlay = () => {
  isPlaying.value ? stopPlay() : startPlay();
};

const startPlay = () => {
  isPlaying.value = true;
  playInterval = setInterval(() => {
    if (selectedWeekIndex.value < weeks.value.length - 1) {
      selectedWeekIndex.value++;
    } else {
      selectedWeekIndex.value = 0;
    }
  }, 1500); // 1.5 segundos por salto
};

const stopPlay = () => {
  isPlaying.value = false;
  if (playInterval) clearInterval(playInterval);
};

watch(selectedWeekIndex, () => {
  loadWeekData();
});

// --- ESTILOS ---
const getColor = (d) => {
  return d > 1000 ? '#800026' :
         d > 500  ? '#BD0026' :
         d > 200  ? '#E31A1C' :
         d > 100  ? '#FC4E2A' :
         d > 50   ? '#FD8D3C' :
         d > 20   ? '#FEB24C' :
         d > 0    ? '#FED976' : '#FFEDA0';
};

const styleFeature = (feature) => {
  return {
    fillColor: getColor(feature.properties.casos || 0), // Ajusta si tu propiedad se llama diferente
    weight: 1,
    opacity: 1,
    color: 'white',
    dashArray: '3',
    fillOpacity: 0.7
  };
};

const onEachFeature = (feature, layer) => {
  const props = feature.properties;
  const nombre = props.NM_MUN || props.name || "Municipio"; 
  const popupContent = `
    <strong>Municipio:</strong> ${nombre}<br/>
    <strong>Casos:</strong> ${props.casos || 0}
  `;
  layer.bindPopup(popupContent);
};
</script>

<style scoped>
/* LAYOUT: Pantalla dividida (Izquierda controles, Derecha mapa) */
.layout-container {
  display: flex;
  height: calc(100vh - 60px); /* Restamos header si existe */
  overflow: hidden;
}

/* SIDEBAR */
.sidebar {
  width: 300px;
  background: #f8f9fa;
  border-right: 1px solid #ddd;
  display: flex;
  flex-direction: column;
  padding: 1rem;
  box-shadow: 2px 0 5px rgba(0,0,0,0.05);
  z-index: 2;
}

.controls-box {
  margin-bottom: 20px;
  background: white;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid #eee;
}

.selectors {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.form-group {
  flex: 1;
}
.form-group label {
  display: block;
  font-size: 0.8rem;
  color: #666;
  margin-bottom: 2px;
}
select {
  width: 100%;
  padding: 5px;
  border-radius: 4px;
  border: 1px solid #ccc;
}

.slider-container {
  text-align: center;
}
.slider {
  width: 100%;
  cursor: pointer;
}
.slider-label {
  font-weight: bold;
  color: #2c3e50;
  margin-top: 5px;
}

/* TABLA */
.table-container {
  flex: 1; /* Ocupa el espacio restante */
  display: flex;
  flex-direction: column;
  background: white;
  border: 1px solid #eee;
  border-radius: 8px;
  overflow: hidden;
}
.table-container h3 {
  font-size: 1rem;
  margin: 10px;
  color: #34495e;
}

.table-scroll {
  flex: 1;
  overflow-y: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
th {
  background: #eee;
  position: sticky;
  top: 0;
  padding: 8px;
  text-align: left;
  font-size: 0.8rem;
}
td {
  padding: 8px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
}
tr:hover {
  background-color: #e3f2fd;
}
.cases-cell {
  font-weight: bold;
  color: #e74c3c;
  text-align: right;
}

/* MAPA */
.map-area {
  flex: 1;
  position: relative;
}
.map-frame {
  width: 100%;
  height: 100%;
}
.map-loader {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(255,255,255,0.9);
  padding: 20px;
  border-radius: 10px;
  font-weight: bold;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 10px;
}
.spinner {
  width: 20px;
  height: 20px;
  border: 3px solid #f3f3f3;
  border-top: 3px solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

/* LEYENDA */
.legend-box {
  margin-bottom: 15px;
  padding: 10px;
  background: white;
  border-radius: 4px;
}
.gradient-bar {
  height: 10px;
  background: linear-gradient(to right, #FFEDA0, #800026);
  border-radius: 2px;
}
.labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  margin-top: 4px;
}


/* Nuevo contenedor para alinear horizontalmente */
.slider-row {
  display: flex;
  align-items: center;
  gap: 10px; /* Espacio entre flechas y slider */
}

/* Estilo de los botones de flecha */
.nav-btn {
  background: #3498db;
  color: white;
  border: none;
  border-radius: 50%; /* Redondos */
  width: 30px;
  height: 30px;
  cursor: pointer;
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.nav-btn:hover:not(:disabled) {
  background: #2980b9;
}

.nav-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
  opacity: 0.5;
}

/* Ajuste para que el slider ocupe el espacio restante */
.slider {
  flex: 1; 
  cursor: pointer;
}
</style>