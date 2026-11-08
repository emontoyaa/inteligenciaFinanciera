import sys
from datetime import date

import pandas as pd
import requests
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output

# ----------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------
URL_TRM = "https://www.datos.gov.co/resource/32sa-8pi3.json"
FECHA_INICIO = "2021-01-01"
REFRESCO_MS = 10 * 60 * 1000  # el dashboard vuelve a consultar los datos cada 10 min

# Paleta Okabe-Ito: distinguible para personas con daltonismo
PALETA = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442"]
COLOR_TEXTO = "#1a1a1a"      # contraste alto sobre fondo blanco
COLOR_MEDIANA = "#000000"

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# ----------------------------------------------------------------------------
# Datos
# ----------------------------------------------------------------------------
def _desde_datos_gov() -> pd.DataFrame:
    params = {
        "$select": "vigenciadesde, valor",
        "$where": f"vigenciadesde >= '{FECHA_INICIO}T00:00:00'",
        "$order": "vigenciadesde ASC",
        "$limit": 50000,
    }
    r = requests.get(URL_TRM, params=params, timeout=20)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["Fecha"] = pd.to_datetime(df["vigenciadesde"])
    df["USD_COP"] = pd.to_numeric(df["valor"])
    return df[["Fecha", "USD_COP"]]


def _desde_yahoo() -> pd.DataFrame:
    import yfinance as yf
    h = yf.download("COP=X", start=FECHA_INICIO, progress=False, auto_adjust=True)
    h = h["Close"].squeeze().dropna().reset_index()
    h.columns = ["Fecha", "USD_COP"]
    return h


def cargar_datos():
    """Devuelve (DataFrame, nombre_de_la_fuente). Prueba varias fuentes en orden."""
    for nombre, funcion in (("TRM oficial (datos.gov.co)", _desde_datos_gov),
                            ("Yahoo Finance (COP=X)", _desde_yahoo)):
        try:
            df = funcion()
            if not df.empty:
                df = df.drop_duplicates("Fecha").sort_values("Fecha")
                df["Año"] = df["Fecha"].dt.year.astype(str)
                df["Trimestre"] = df["Fecha"].dt.year.astype(str) + "-T" + df["Fecha"].dt.quarter.astype(str)
                df["Mes"] = df["Fecha"].dt.strftime("%Y-%m")
                return df.reset_index(drop=True), nombre
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] No se pudo usar {nombre}: {e}")
    raise RuntimeError("No fue posible descargar datos reales. Revisa tu conexión a internet.")


# ----------------------------------------------------------------------------
# Gráfica
# ----------------------------------------------------------------------------
def crear_figura(df: pd.DataFrame, agrupar: str, mostrar_puntos: bool, mostrar_media: bool) -> go.Figure:
    grupos = sorted(df[agrupar].unique())
    fig = go.Figure()

    for i, g in enumerate(grupos):
        datos = df[df[agrupar] == g]
        color = PALETA[i % len(PALETA)]
        fig.add_trace(go.Box(
            y=datos["USD_COP"],
            x=[g] * len(datos),
            name=g,
            boxmean=mostrar_media,                     # línea punteada = media
            boxpoints="all" if mostrar_puntos else "outliers",
            jitter=0.5, pointpos=0, marker=dict(size=3, opacity=0.25, color=color),
            line=dict(color=COLOR_MEDIANA, width=1.6),
            fillcolor=color, opacity=0.9,
            customdata=datos["Fecha"].dt.strftime("%d/%m/%Y"),
            hovertemplate="<b>%{x}</b><br>Fecha: %{customdata}<br>"
                          "TRM: $%{y:,.2f} COP<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(
        title=dict(text="Distribución del dólar en Colombia (USD/COP)",
                   font=dict(size=22, color=COLOR_TEXTO), x=0.02),
        xaxis=dict(title=dict(text=f"Periodo ({agrupar.lower()})", font=dict(size=15)),
                   tickfont=dict(size=13), tickangle=-45 if len(grupos) > 8 else 0,
                   type="category"),
        yaxis=dict(title=dict(text="Pesos colombianos por 1 dólar (COP)", font=dict(size=15)),
                   tickprefix="$", tickformat=",.0f", tickfont=dict(size=13),
                   gridcolor="#d9d9d9", zeroline=False),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(color=COLOR_TEXTO, family="Arial, sans-serif"),
        hoverlabel=dict(bgcolor="white", font_size=14, font_color=COLOR_TEXTO),
        margin=dict(l=80, r=30, t=70, b=90),
        height=560,
    )
    return fig


def resumen_texto(df: pd.DataFrame) -> str:
    """Descripción en texto de la gráfica (para lectores de pantalla)."""
    ult = df.iloc[-1]
    max_g = df.loc[df["USD_COP"].idxmax()]
    min_g = df.loc[df["USD_COP"].idxmin()]
    return (f"Último valor: ${ult.USD_COP:,.2f} COP el {ult.Fecha:%d/%m/%Y}. "
            f"Mediana del periodo: ${df.USD_COP.median():,.2f}. "
            f"Máximo: ${max_g.USD_COP:,.2f} ({max_g.Fecha:%d/%m/%Y}). "
            f"Mínimo: ${min_g.USD_COP:,.2f} ({min_g.Fecha:%d/%m/%Y}).")


# ----------------------------------------------------------------------------
# Aplicación Dash
# ----------------------------------------------------------------------------
def tarjeta(titulo, valor):
    return html.Div([
        html.Div(titulo, style={"fontSize": "14px", "color": "#444"}),
        html.Div(valor, style={"fontSize": "26px", "fontWeight": "bold", "color": COLOR_TEXTO}),
    ], style={"border": "2px solid #0072B2", "borderRadius": "10px", "padding": "10px 18px",
              "minWidth": "190px", "background": "#f7fbff"})


def crear_app() -> Dash:
    app = Dash(__name__, title="Dólar USD/COP – Box Plot")
    app.layout = html.Div(lang="es", style={"fontFamily": "Arial, sans-serif", "maxWidth": "1200px",
                                             "margin": "0 auto", "padding": "16px", "color": COLOR_TEXTO}, children=[
        html.H1("Comportamiento del dólar en Colombia (USD/COP)"),
        html.P("Cada caja resume un periodo: la línea negra es la mediana, la caja contiene el 50 % central "
               "de los valores (Q1–Q3) y los bigotes muestran el rango normal. Los puntos fuera son valores atípicos."),

        html.Div(id="tarjetas", style={"display": "flex", "gap": "14px", "flexWrap": "wrap", "margin": "12px 0"}),

        html.Div([
            html.Div([
                html.Label("Agrupar por:", htmlFor="agrupar", style={"fontWeight": "bold"}),
                dcc.RadioItems(id="agrupar", value="Año", inline=True,
                               options=[{"label": " Año", "value": "Año"},
                                        {"label": " Trimestre", "value": "Trimestre"},
                                        {"label": " Mes", "value": "Mes"}],
                               labelStyle={"marginRight": "16px", "fontSize": "16px"}),
            ]),
            html.Div([
                html.Label("Opciones:", style={"fontWeight": "bold"}),
                dcc.Checklist(id="opciones", value=["media"], inline=True,
                              options=[{"label": " Mostrar todos los datos", "value": "puntos"},
                                       {"label": " Mostrar media (línea punteada)", "value": "media"}],
                              labelStyle={"marginRight": "16px", "fontSize": "16px"}),
            ]),
        ], style={"display": "flex", "gap": "40px", "flexWrap": "wrap", "marginBottom": "8px"}),

        html.Div([
            html.Label("Rango de años:", style={"fontWeight": "bold"}),
            dcc.RangeSlider(id="anios", min=2021, max=date.today().year, step=1,
                            value=[2021, date.today().year],
                            marks={y: str(y) for y in range(2021, date.today().year + 1)}),
        ], style={"margin": "10px 0 20px"}),

        dcc.Graph(id="grafica", config={"displaylogo": False, "toImageButtonOptions": {"filename": "usd_cop_boxplot"}}),

        html.P(id="descripcion", role="status", **{"aria-live": "polite"}, style={"fontSize": "16px"}),
        html.P(id="fuente", style={"fontSize": "13px", "color": "#555"}),

        dcc.Interval(id="reloj", interval=REFRESCO_MS, n_intervals=0),  # actualización automática
    ])

    @app.callback(
        Output("grafica", "figure"), Output("tarjetas", "children"),
        Output("descripcion", "children"), Output("fuente", "children"),
        Input("agrupar", "value"), Input("opciones", "value"),
        Input("anios", "value"), Input("reloj", "n_intervals"),
    )
    def actualizar(agrupar, opciones, anios, _):
        df, fuente = cargar_datos()                      # datos frescos en cada actualización
        df = df[(df["Fecha"].dt.year >= anios[0]) & (df["Fecha"].dt.year <= anios[1])]
        fig = crear_figura(df, agrupar, "puntos" in opciones, "media" in opciones)
        ult = df.iloc[-1]
        tarjetas = [tarjeta("Último valor", f"${ult.USD_COP:,.2f}"),
                    tarjeta("Mediana", f"${df.USD_COP.median():,.2f}"),
                    tarjeta("Máximo", f"${df.USD_COP.max():,.2f}"),
                    tarjeta("Mínimo", f"${df.USD_COP.min():,.2f}")]
        pie = f"Fuente: {fuente}. Actualizado: {pd.Timestamp.now():%d/%m/%Y %H:%M}. Se refresca cada 10 minutos."
        return fig, tarjetas, resumen_texto(df), pie

    return app
app = crear_app()
server = app.server

if __name__ == "__main__":
    if "--html" in sys.argv:
        datos, _ = cargar_datos()
        figura = crear_figura(datos, "Año", mostrar_puntos=False, mostrar_media=True)
        figura.write_html("usd_cop_boxplot.html", include_plotlyjs="cdn")
        print("Archivo generado: usd_cop_boxplot.html")
    else:
        app.run(debug=False)
