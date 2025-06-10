from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import snowflake.connector
from decimal import Decimal
import os
from dotenv import load_dotenv
import google.generativeai as genai
import json

app = Flask(__name__)
CORS(app, resources={r"/query": {"origins": "*"}})  # Permitir solicitudes a /query desde cualquier origen

# Cargar variables de entorno
load_dotenv()

# Configurar Google Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
instruction = """Eres un experto en interactuar con una base de datos Snowflake y en análisis de movilidad urbana en NYC con datos de CitiBike. 
Tu objetivo es responder preguntas en lenguaje natural generando consultas SQL válidas para Snowflake.
Tienes estas funciones:
- obtener_tablas_snowflake(): Lista las tablas disponibles.
- obtener_esquema_tabla_snowflake(table_name: string): Devuelve el esquema de una tabla.
- ejecutar_consulta_snowflake(sql_query: string): Ejecuta una consulta SQL y devuelve resultados.

Tablas disponibles y sus columnas:
- CLIMA_CITI_NYC: Datos de clima (Date, AWND (viento), PRCP (Precipitacion o lluvia), SNOW, TMAX (Temperatura maxima en celcius),TMIN (Temperatura minima en celcius))
- DIM_BICICLETA: BikeID y TIPO_BICICLETA (eléctrica, normal).
- DIM_ESTACION: Estaciones de CitiBike (STATION_ID, NOMBRE_ESTACION, LATITUD, LONGITUD).
- DIM_TIEMPO: TIME_ID, FECHA, ANO, MES, DIA, HORA, DIA_SEMANA.
- DIM_USUARIO: USER_TYPE_ID, TIPO_USUARIO (Con membresia o casual).
- FREC_VIAJES: RIDE_ID, TIME_ID, START_STATION_ID, END_STATION_ID, USER_TYPE_ID, BIKE_TYPE_ID, DURACION_VIAJE, NUMERO_VIAJES, FLUJO_NETO.
- MAESTRA: (Datos completos de viajes), columnas: RIDE_ID,RIDEABLE_TYPE,STARTED_AT,ENDED_AT,START_STATION_NAME,START_STATION_ID,END_STATION_NAME,END_STATION_ID,START_LAT,START_LNG,END_LAT,END_LNG,MEMBER_CASUAL
- TRAFICO_HISTORICO_DOT: REQUEST_ID, BORO (ciudad o colonia), YR (año), M(mes), D(dia), HH(hora), MM(minutos), VOL (Volumnen del trafico), SEGMENT_ID, WKT_GEOM, STREET(Nombre de la calle), FROM_ST, TO_ST, DIRECTION.

Genera consultas SQL precisas usando el dialecto de Snowflake y los nombres exactos de las columnas (por ejemplo, usa STREET, VOL, HH para TRAFICO_HISTORICO_DOT). Incluye la consulta SQL entre ```sql y ```, y menciona la tabla usada con 'Saqué este resultado de la tabla `NOMBRE_TABLA`'. 
Responde en lenguaje natural con la consulta SQL y una breve explicación. No digas que no puedes ejecutar la consulta, ya que el sistema lo hará automáticamente con `ejecutar_consulta_snowflake()`."""

# Funciones de Snowflake
def obtener_tablas_snowflake():
    account = os.getenv("SNOWFLAKE_ACCOUNT")
    user = os.getenv("SNOWFLAKE_USER")
    password = os.getenv("SNOWFLAKE_PASSWORD")
    database = "CITIBIKE"
    schema = "PUBLIC"

    tables = []
    try:
        conn = snowflake.connector.connect(
            account=account,
            user=user,
            password=password,
            database=database,
            schema=schema
        )
        cursor = conn.cursor()
        sql = f"SHOW TABLES IN {database}.{schema}"
        cursor.execute(sql)
        for row in cursor:
            tables.append(row[1])
    except snowflake.connector.errors.Error as e:
        print(f"Error al conectar o ejecutar la consulta en Snowflake: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()
    return tables

def obtener_esquema_tabla_snowflake(table_name: str):
    account = os.getenv("SNOWFLAKE_ACCOUNT")
    user = os.getenv("SNOWFLAKE_USER")
    password = os.getenv("SNOWFLAKE_PASSWORD")
    database = "CITIBIKE"
    schema = "PUBLIC"

    schema_info = []
    try:
        conn = snowflake.connector.connect(
            account=account,
            user=user,
            password=password,
            database=database,
            schema=schema
        )
        cursor = conn.cursor()
        sql = f"DESCRIBE TABLE {database}.{schema}.{table_name}"
        cursor.execute(sql)
        for row in cursor:
            schema_info.append({"name": row[0], "type": row[1]})
    except snowflake.connector.errors.Error as e:
        print(f"Error al conectar o ejecutar la consulta en Snowflake: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()
    return schema_info

def ejecutar_consulta_snowflake(sql_query: str):
    account = os.getenv("SNOWFLAKE_ACCOUNT")
    user = os.getenv("SNOWFLAKE_USER")
    password = os.getenv("SNOWFLAKE_PASSWORD")
    database = "CITIBIKE"
    schema = "PUBLIC"

    results = []
    conn = None
    try:
        conn = snowflake.connector.connect(
            account=account,
            user=user,
            password=password,
            database=database,
            schema=schema
        )
        cursor = conn.cursor()
        print(f"Ejecutando consulta SQL: {sql_query}")  # Depuración
        cursor.execute(sql_query)
        column_names = [col[0] for col in cursor.description]
        for row in cursor:
            row_dict = {}
            for i, col_name in enumerate(column_names):
                if isinstance(row[i], Decimal):
                    row_dict[col_name] = float(row[i])
                else:
                    row_dict[col_name] = row[i]
            results.append(row_dict)
        print(f"Resultados crudos: {results}")  # Depuración
    except snowflake.connector.errors.Error as e:
        print(f"Error al ejecutar la consulta en Snowflake: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()
    return results

# Configurar cliente de Gemini
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction=instruction,
    tools=[obtener_tablas_snowflake, obtener_esquema_tabla_snowflake, ejecutar_consulta_snowflake]
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/query", methods=["POST"])
def query_snowflake():
    try:
        data = request.get_json()
        user_query = data.get("query")

        # Iniciar sesión de chat con Gemini
        chat_session = model.start_chat(history=[])
        resp = chat_session.send_message(user_query)

        # Manejar la respuesta de Gemini
        response_text = ""
        sql_query = ""
        table_used = ""
        results = []

        # Inspeccionar las partes de la respuesta
        print(f"Partes de la respuesta: {resp.parts}")  # Depuración
        for part in resp.parts:
            if hasattr(part, 'text') and part.text:
                response_text += part.text
                print(f"Texto en la respuesta: {part.text}")  # Depuración
            elif hasattr(part, 'function_call') and part.function_call:
                # Manejar la llamada a la función
                func_name = part.function_call.name
                func_args = part.function_call.args
                print(f"Function call: {func_name}, args: {func_args}")  # Depuración

                if func_name == "obtener_tablas_snowflake":
                    tables = obtener_tablas_snowflake()
                    response_text += f"Tablas disponibles: {', '.join(tables)}"
                elif func_name == "obtener_esquema_tabla_snowflake":
                    table_name = func_args.get("table_name")
                    schema = obtener_esquema_tabla_snowflake(table_name)
                    response_text += f"Esquema de {table_name}: {json.dumps(schema, indent=2)}"
                elif func_name == "ejecutar_consulta_snowflake":
                    sql_query = func_args.get("sql_query")
                    print(f"Ejecutando consulta SQL desde function_call: {sql_query}")  # Depuración
                    results = ejecutar_consulta_snowflake(sql_query)
                    print(f"Resultados crudos desde function_call: {results}")  # Depuración
                    response_text += f"Resultados de la consulta: {json.dumps(results, indent=2)}"
                    if "Saqué este resultado de la tabla" in response_text:
                        table_start = response_text.index("Saqué este resultado de la tabla") + 33
                        table_end = response_text.index("`", table_start)
                        table_used = response_text[table_start:table_end]

        # Extraer consulta SQL del texto si no viene en function_call
        if "```sql" in response_text and not sql_query:
            sql_start = response_text.index("```sql") + 6
            sql_end = response_text.index("```", sql_start)
            sql_query = response_text[sql_start:sql_end].strip()
            print(f"Consulta SQL extraída del texto: {sql_query}")  # Depuración
            if sql_query:
                results = ejecutar_consulta_snowflake(sql_query)
                print(f"Resultados crudos desde texto: {results}")  # Depuración
                response_text += f"\nResultados obtenidos: {json.dumps(results, indent=2)}"
                if "Saqué este resultado de la tabla" in response_text:
                    table_start = response_text.index("Saqué este resultado de la tabla") + 33
                    table_end = response_text.index("`", table_start)
                    table_used = response_text[table_start:table_end]

        print(f"Respuesta final: {response_text}")  # Depuración
        return jsonify({
            "status": "success",
            "response": response_text,
            "sql_query": sql_query,
            "table_used": table_used,
            "results": results
        })

    except Exception as e:
        print(f"Error en query_snowflake: {str(e)}")  # Depuración
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == "__main__":
    app.run(debug=True)