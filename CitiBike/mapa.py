# Generar un mapa interactivo con las estaciones de bicicletas y su demanda
import pandas as pd
import folium
from folium import plugins
import numpy as np

# Cargar el CSV de predicciones
pred_df = pd.read_csv('bicicletas_necesarias_2025_2026_todas_estaciones.csv.gz')

# Cargar citi.csv para obtener coordenadas
citi_df = pd.read_csv('citi.csv')
citi_df['START_STATION_ID'] = citi_df['START_STATION_ID'].astype(int)

# Obtener coordenadas únicas por estación
stations_coords = citi_df[['START_STATION_ID', 'NOMBRE_ESTACION', 'LATITUD', 'LONGITUD']].drop_duplicates()

# Verificar estaciones
print("Estaciones en predicciones:", pred_df['START_STATION_ID'].unique())
print("Estaciones con coordenadas:", stations_coords['START_STATION_ID'].unique())

# Filtrar predicciones para el 1 de junio de 2025
pred_df['FECHA'] = pd.to_datetime(pred_df['FECHA'])
date_filter = (pred_df['FECHA'].dt.date == pd.to_datetime('2025-06-01').date())
day_pred_df = pred_df[date_filter].copy()

# Crear un mapa centrado en CDMX
m = folium.Map(location=[19.42847, -99.12766], zoom_start=12)

# Añadir marcador para el centro de CDMX
tooltip = 'Centro de CDMX'
folium.Marker([19.42847, -99.12766], popup='Plaza Mayor', tooltip=tooltip).add_to(m)

# Añadir marcadores para cada estación
for _, station in stations_coords.iterrows():
    station_id = station['START_STATION_ID']
    nombre = station['NOMBRE_ESTACION']
    lat = station['LATITUD']
    lon = station['LONGITUD']
    
    # Obtener demanda por hora para esta estación el 1 de junio de 2025
    station_pred = day_pred_df[day_pred_df['START_STATION_ID'] == station_id]
    if station_pred.empty:
        popup_text = f"<b>{nombre}</b><br>No hay datos para el 1 de junio de 2025"
    else:
        # Crear tabla HTML para la demanda por hora
        popup_text = f"<b>{nombre}</b><br><table border='1'><tr><th>Hora</th><th>Bicicletas Necesarias</th></tr>"
        for hora in range(24):
            demanda = station_pred[station_pred['HORA'] == hora]['BICICLETAS_NECESARIAS'].values
            demanda_val = demanda[0] if len(demanda) > 0 else 0
            popup_text += f"<tr><td>{hora}:00</td><td>{demanda_val}</td></tr>"
        popup_text += "</table>"
    
    # Añadir CircleMarker
    folium.CircleMarker(
        location=[lat, lon],
        radius=5,
        color="cornflowerblue",
        stroke=False,
        fill=True,
        fill_opacity=0.6,
        opacity=1,
        popup=folium.Popup(popup_text, max_width=300),
        tooltip=nombre
    ).add_to(m)

# Opcional: Añadir mapa de calor basado en la demanda promedio diaria
daily_demand = pred_df.groupby(['START_STATION_ID', pred_df['FECHA'].dt.date])['BICICLETAS_NECESARIAS'].sum().reset_index()
daily_demand = daily_demand.merge(stations_coords[['START_STATION_ID', 'LATITUD', 'LONGITUD']], on='START_STATION_ID')
heat_data = [[row['LATITUD'], row['LONGITUD'], row['BICICLETAS_NECESARIAS']] for _, row in daily_demand.iterrows()]
m.add_child(plugins.HeatMap(heat_data, radius=10))

# Guardar mapa en HTML
m.save("mapa_estaciones_demanda.html")
print("Mapa guardado en 'mapa_estaciones_demanda.html'")
