<template>
  <div class="argentina-view">
    <h1>Dengue en Argentina 🇦🇷</h1>
    
    <div v-if="loading" class="loading">Cargando datos...</div>
    <div v-if="error" class="error">Error: {{ error }}</div>

    <div id="map" class="map-container"></div>

    <div class="controls" v-if="weeks.length > 0">
      
      <div class="control-row">
        
        <div class="nav-buttons">
          <button @click="togglePlay" class="btn-play">
            {{ isPlaying ? '⏸ Pausa' : '▶ Play' }}
          </button>
          
          <button @click="prevWeek" :disabled="selectedWeekIndex <= 0" class="btn-step">
            ⏪ Anterior
          </button>
          
          <button @click="nextWeek" :disabled="selectedWeekIndex >= weeks.length - 1" class="btn-step">
            Siguiente ⏩
          </button>
        </div>

        <div class="selectors">
          <label>Año:
            <select v-model="selectedYear" @change="onYearChange">
              <option v-for="y in uniqueYears" :key="y" :value="y">{{ y }}</option>
            </select>
          </label>

          <label>Semana:
            <select v-model="selectedWeekNum" @change="onWeekDropdownChange">
              <option v-for="w in availableWeeksInYear" :key="w" :value="w">
                Semana {{ w }}
              </option>
            </select>
          </label>
        </div>

      </div>
      
      <div class="slider-row">
        <span class="week-display">{{ currentWeek }}</span>
        <input 
          type="range" 
          min="0" 
          :max="weeks.length - 1" 
          v-model.number="selectedWeekIndex"
          class="slider"
        />
      </div>

    </div>

    <div class="legend">
      <h4>Casos Confirmados</h4>
      <div class="legend-item"><span style="background:#800026"></span> > 1000</div>
      <div class="legend-item"><span style="background:#BD0026"></span> 500 - 1000</div>
      <div class="legend-item"><span style="background:#E31A1C"></span> 200 - 500</div>
      <div class="legend-item"><span style="background:#FC4E2A"></span> 100 - 200</div>
      <div class="legend-item"><span style="background:#FD8D3C"></span> 50 - 100</div>
      <div class="legend-item"><span style="background:#FEB24C"></span> 20 - 50</div>
      <div class="legend-item"><span style="background:#FED976"></span> 1 - 20</div>
      <div class="legend-item"><span style="background:#FFEDA0"></span> 0</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, onUnmounted } from 'vue';
import axios from 'axios';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// --- ESTADO ---
const weeks = ref([]); // Lista completa ["2018-01", "2018-02", ...]
const selectedWeekIndex = ref(0);
const loading = ref(false);
const error = ref(null);
const isPlaying = ref(false);
let playInterval = null;

// Variables para los Dropdowns
const selectedYear = ref("");
const selectedWeekNum = ref("");

// Mapa
let map = null;
let geoJsonLayer = null;


const API_URL = import.meta.env.VITE_API_BASE_URL;

const API_BASE = await axios.get(`${API_URL}/api`);


// --- COMPUTADAS ---

// Semana actual en formato "YYYY-WW"
const currentWeek = computed(() => {
  if (weeks.value.length === 0) return '';
  return weeks.value[selectedWeekIndex.value];
});

// Extraer años únicos de la lista de semanas
const uniqueYears = computed(() => {
  const years = new Set(weeks.value.map(w => w.split('-')[0]));
  return Array.from(years).sort();
});

// Filtrar semanas disponibles según el año seleccionado
const availableWeeksInYear = computed(() => {
  if (!selectedYear.value) return [];
  return weeks.value
    .filter(w => w.startsWith(selectedYear.value))
    .map(w => w.split('-')[1]); // Retornar solo el número de semana ("01", "02")
});

// --- CICLO DE VIDA ---
onMounted(async () => {
  initMap();
  await loadWeeks();
});

onUnmounted(() => {
  stopPlay();
});

// --- FUNCIONES LÓGICAS ---

const initMap = () => {
  map = L.map('map').setView([-38.4161, -63.6167], 4);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19
  }).addTo(map);
};

const loadWeeks = async () => {
  try {
    loading.value = true;
    const res = await axios.get(`${API_BASE}/argentina/weeks`);
    weeks.value = res.data;
    
    // Seleccionar la última semana por defecto
    if (weeks.value.length > 0) {
      selectedWeekIndex.value = weeks.value.length - 1;
      syncDropdownsFromIndex(); // Sincronizar dropdowns iniciales
    }
  } catch (e) {
    error.value = "Error cargando semanas: " + e.message;
  } finally {
    loading.value = false;
  }
};

const loadWeekData = async () => {
  if (!currentWeek.value) return;
  try {
    // loading.value = true; // Opcional: quitar para que no parpadee al reproducir
    const res = await axios.get(`${API_BASE}/argentina/data`, {
      params: { week: currentWeek.value }
    });
    const data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
    updateMapLayer(data);
  } catch (e) {
    console.error("Error geojson:", e);
  } finally {
    // loading.value = false;
  }
};

const updateMapLayer = (data) => {
  if (geoJsonLayer) map.removeLayer(geoJsonLayer);
  geoJsonLayer = L.geoJSON(data, {
    style: styleFeature,
    onEachFeature: onEachFeature
  }).addTo(map);
};

// --- SINCRONIZACIÓN DROPDOWNS <-> SLIDER ---

// 1. Cuando se mueve el slider (o play), actualizamos los variables de los dropdowns
const syncDropdownsFromIndex = () => {
  const current = weeks.value[selectedWeekIndex.value];
  if (current) {
    const [y, w] = current.split('-');
    selectedYear.value = y;
    selectedWeekNum.value = w;
  }
};

// 2. Cuando el usuario cambia el AÑO manualmente
const onYearChange = () => {
  // Buscamos la primera semana disponible de ese año
  const target = weeks.value.find(w => w.startsWith(selectedYear.value));
  if (target) {
    selectedWeekIndex.value = weeks.value.indexOf(target);
    // El watcher de selectedWeekIndex se encargará de actualizar el mapa y el weekNum
  }
};

// 3. Cuando el usuario cambia la SEMANA manualmente
const onWeekDropdownChange = () => {
  const target = `${selectedYear.value}-${selectedWeekNum.value}`;
  const idx = weeks.value.indexOf(target);
  if (idx !== -1) {
    selectedWeekIndex.value = idx;
  }
};

// --- CONTROLES DE NAVEGACIÓN ---

const prevWeek = () => {
  if (selectedWeekIndex.value > 0) {
    selectedWeekIndex.value--;
  }
};

const nextWeek = () => {
  if (selectedWeekIndex.value < weeks.value.length - 1) {
    selectedWeekIndex.value++;
  }
};

const togglePlay = () => {
  if (isPlaying.value) stopPlay();
  else startPlay();
};

const startPlay = () => {
  isPlaying.value = true;
  playInterval = setInterval(() => {
    if (selectedWeekIndex.value < weeks.value.length - 1) {
      selectedWeekIndex.value++;
    } else {
      selectedWeekIndex.value = 0; // Loop
    }
  }, 1000);
};

const stopPlay = () => {
  isPlaying.value = false;
  if (playInterval) clearInterval(playInterval);
};

// --- WATCHERS ---

// Watch principal: Si cambia el índice (por slider, play o botones), cargar datos y actualizar dropdowns
watch(selectedWeekIndex, () => {
  loadWeekData();
  syncDropdownsFromIndex();
});

// --- ESTILOS MAPA ---
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
    fillColor: getColor(feature.properties.CONFIRMADO || 0),
    weight: 1,
    opacity: 1,
    color: 'white',
    dashArray: '3',
    fillOpacity: 0.7
  };
};

const onEachFeature = (feature, layer) => {
  const props = feature.properties;
  
  // Como hicimos merge, props.DEPARTAMENTO (del CSV) podría existir si hubo cruce,
  // si no, usamos el del Shapefile (props.departamen o similar).
  const nombre = props.DEPARTAMENTO || props.departamen || "Desconocido";

  const popupContent = `
    <strong>Provincia:</strong> ${props.PROVINCIA || props.provincia}<br/>
    <strong>Depto:</strong> ${nombre}<br/>
    <strong>Confirmados:</strong> ${props.CONFIRMADO || 0}
  `;
  
  layer.bindPopup(popupContent);
  
  layer.on({
    mouseover: (e) => {
      const layer = e.target;
      layer.setStyle({ weight: 2, color: '#666', dashArray: '', fillOpacity: 0.9 });
      layer.bringToFront();
    },
    mouseout: (e) => {
      geoJsonLayer.resetStyle(e.target);
    }
  });
};
</script>

<style scoped>
.argentina-view {
  display: flex;
  flex-direction: column;
  height: 90vh;
  font-family: 'Segoe UI', sans-serif;
  position: relative;
}

h1 { text-align: center; margin: 10px 0; color: #333; font-size: 1.5rem; }

.map-container {
  flex-grow: 1;
  width: 100%;
  border: 1px solid #ddd;
  background: #f0f0f0;
}

/* --- PANEL DE CONTROLES MEJORADO --- */
.controls {
  padding: 15px;
  background: #fff;
  border-top: 1px solid #ddd;
  display: flex;
  flex-direction: column;
  gap: 15px;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
}

.control-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 15px;
}

.nav-buttons {
  display: flex;
  gap: 5px;
}

.selectors {
  display: flex;
  gap: 15px;
  align-items: center;
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 15px;
}

.week-display {
  font-weight: bold;
  font-size: 1.1rem;
  color: #2c3e50;
  min-width: 80px;
}

.slider {
  flex-grow: 1;
  cursor: pointer;
}

/* Botones */
button {
  padding: 6px 12px;
  cursor: pointer;
  border: none;
  border-radius: 4px;
  font-size: 0.9rem;
  transition: background 0.2s;
}

.btn-play {
  background-color: #28a745;
  color: white;
  min-width: 80px;
}
.btn-play:hover { background-color: #218838; }

.btn-step {
  background-color: #007bff;
  color: white;
}
.btn-step:hover { background-color: #0056b3; }
.btn-step:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

/* Selects */
select {
  padding: 5px;
  border-radius: 4px;
  border: 1px solid #ccc;
  font-size: 0.9rem;
}

/* Leyenda */
.legend {
  position: absolute;
  bottom: 150px; /* Ajustado para que no tape controles */
  right: 20px;
  background: rgba(255, 255, 255, 0.9);
  padding: 10px;
  border-radius: 5px;
  box-shadow: 0 0 10px rgba(0,0,0,0.2);
  z-index: 1000;
  font-size: 12px;
}

.legend h4 { margin: 0 0 5px 0; font-size: 14px; }
.legend-item { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; }
.legend-item span { width: 15px; height: 15px; display: inline-block; border: 1px solid #ccc; }

.loading, .error { text-align: center; padding: 20px; font-weight: bold; }
.error { color: red; }
</style>