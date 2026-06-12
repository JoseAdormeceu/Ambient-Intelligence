"""
GeoSensing & Community Hub v4
"""
import sys, os, time
from qgis.utils import iface
from qgis.PyQt.QtWidgets import (
    QApplication, QLabel, QComboBox, QFileDialog, QPushButton,
    QVBoxLayout, QHBoxLayout, QTextEdit, QDialog, QLineEdit,
    QGroupBox, QRadioButton, QButtonGroup, QStackedWidget, QWidget,
    QSpinBox, QDoubleSpinBox, QMessageBox
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt

# ─── CONFIGURACAO ─────────────────────────────────────────
DEFAULT_PASTA_PORTUGAL = r"C:\Users\josem\Desktop\AI 2\portugal"
DEFAULT_PASTA_OUTPUT   = r"C:\Users\josem\Desktop\AI 2\output"
ORS_API_KEY            = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImE4ZTk5MGRjYzFkMDc0MzRjMDJkNGM2OWEyZGY0ZGYzMmQyM2JmZmU2YTBmODFlNzFmOWIzODFlIiwiaCI6Im11cm11cjY0In0="
ISEC_LAT               = "40.193131"
ISEC_LON               = "-8.409922"
CATEGORIAS_CONFIAVEIS  = ["hospital", "school", "pharmacy", "parking"]
BBOXES = {
    "Coimbra": (-8.6, 40.1, -8.3, 40.3),
    "Porto":   (-8.7, 41.1, -8.5, 41.3),
    "Lisboa":  (-9.3, 38.6, -9.0, 38.8),
}
ORS_PERFIS = {
    "Carro":     "driving-car",
    "A Pe":      "foot-walking",
    "Bicicleta": "cycling-regular",
}
GEOSENSING_LAYERS = [
    ("GeoSensing — Reporting", "reporting.gpkg"),
    ("GeoSensing — Events",    "events.gpkg"),
    ("GeoSensing — POIs",      "pois_geosensing.gpkg"),
]

# ─── WIDGETS GLOBAIS ──────────────────────────────────────
app               = QApplication.instance() or QApplication(sys.argv)
log_text          = QTextEdit()
combo_cidade      = QComboBox()
combo_categoria   = QComboBox()
combo_transporte  = QComboBox()
combo_rota_pref   = QComboBox()
spin_top_clusters = QSpinBox()
edit_output       = QLineEdit()
edit_origem_lat   = QLineEdit()
edit_origem_lon   = QLineEdit()
edit_dest_lat     = QLineEdit()
edit_dest_lon     = QLineEdit()
edit_dest_texto   = QLineEdit()
edit_edificios     = QLineEdit()
radio_coords      = QRadioButton("Coordenadas")
radio_texto       = QRadioButton("Morada / Edificio")
stack_destino     = QStackedWidget()

# Parametros configuráveis
spin_buffer_m      = QSpinBox()
spin_dbscan_min    = QSpinBox()
dspin_dbscan_eps   = QDoubleSpinBox()
dspin_heatmap_raio = QDoubleSpinBox()
spin_iso1          = QSpinBox()
spin_iso2          = QSpinBox()

# GeoSensing / Mergin Maps


# ─── HELPERS ──────────────────────────────────────────────
def log(msg):
    log_text.append(str(msg))
    QApplication.processEvents()

def separador():
    log("─" * 40)

def selecionar_pasta(edit_widget, default):
    pasta = QFileDialog.getExistingDirectory(None, "Selecionar pasta", default)
    if pasta:
        edit_widget.setText(pasta)

def adicionar_layer(caminho, nome):
    from qgis.core import QgsVectorLayer, QgsProject
    for lyr in list(QgsProject.instance().mapLayers().values()):
        if lyr.name() == nome:
            QgsProject.instance().removeMapLayer(lyr)
    time.sleep(0.3)
    lyr = QgsVectorLayer(caminho, nome, "ogr")
    if lyr.isValid():
        QgsProject.instance().addMapLayer(lyr)
        log(f"  [OK] {nome} ({lyr.featureCount()} features)")
        return lyr
    log(f"  [ERRO] Layer invalido: {caminho}")
    return None

def guardar_geojson(gdf, caminho):
    from qgis.core import QgsProject
    # Remover do QGIS qualquer layer que use este ficheiro antes de apagar
    for lyr in list(QgsProject.instance().mapLayers().values()):
        src = lyr.source().split("|")[0]
        if os.path.normpath(src) == os.path.normpath(caminho):
            QgsProject.instance().removeMapLayer(lyr)
    time.sleep(0.2)
    if os.path.exists(caminho):
        os.remove(caminho)
    gdf2 = gdf.copy()
    for col in gdf2.columns:
        if col != 'geometry':
            gdf2[col] = gdf2[col].astype(str)
    gdf2.to_file(caminho, driver="GeoJSON")

def geocodificar(texto, cidade):
    import requests
    url    = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"{texto}, {cidade}, Portugal", "format": "json", "limit": 1}
    try:
        r   = requests.get(url, params=params, headers={"User-Agent": "GeoSensing/4.0"}, timeout=10)
        res = r.json()
        if res:
            lat, lon = float(res[0]["lat"]), float(res[0]["lon"])
            log(f"  [Geocod] {texto} -> {lat:.5f}, {lon:.5f}")
            return lat, lon
        log(f"  [ERRO] Geocodificacao sem resultado: {texto}")
    except Exception as e:
        log(f"  [ERRO] Geocodificacao: {e}")
    return None, None

def obter_destino():
    if radio_texto.isChecked():
        texto = edit_dest_texto.text().strip()
        if not texto:
            return None, None
        return geocodificar(texto, combo_cidade.currentText())
    else:
        try:
            return float(edit_dest_lat.text()), float(edit_dest_lon.text())
        except:
            return None, None

def aplicar_simbologia_heatmap(lyr):
    from qgis.core import QgsRasterShader, QgsColorRampShader, QgsSingleBandPseudoColorRenderer
    provider = lyr.dataProvider()
    vmax     = provider.bandStatistics(1).maximumValue
    shader   = QgsRasterShader()
    cr       = QgsColorRampShader()
    cr.setColorRampType(QgsColorRampShader.Type.Interpolated)
    cr.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(0,        QColor(255,255,204,0),   '0'),
        QgsColorRampShader.ColorRampItem(vmax*0.2, QColor(255,237,160,180), 'baixo'),
        QgsColorRampShader.ColorRampItem(vmax*0.5, QColor(254,178,76,200),  'medio'),
        QgsColorRampShader.ColorRampItem(vmax*0.8, QColor(240,59,32,220),   'alto'),
        QgsColorRampShader.ColorRampItem(vmax,     QColor(189,0,38,255),    'maximo'),
    ])
    shader.setRasterShaderFunction(cr)
    lyr.setRenderer(QgsSingleBandPseudoColorRenderer(provider, 1, shader))
    lyr.triggerRepaint()

def aplicar_simbologia_vetor(lyr, cor_hex, opacidade):
    from qgis.core import QgsFillSymbol
    symbol = QgsFillSymbol.createSimple({'color': cor_hex, 'outline_color': cor_hex, 'outline_width': '0.5'})
    symbol.setOpacity(opacidade)
    lyr.renderer().setSymbol(symbol)
    lyr.triggerRepaint()

def recarregar_layers_geosensing():
    """Recarrega as 3 camadas GeoSensing do disco para o QGIS."""
    pasta_proj = edit_output.text() or DEFAULT_PASTA_OUTPUT
    log("  Camadas GeoSensing:")
    ok = 0
    for nome, fich in GEOSENSING_LAYERS:
        caminho = os.path.join(pasta_proj, fich)
        if os.path.exists(caminho):
            lyr = adicionar_layer(caminho, nome)
            if lyr:
                ok += 1
        else:
            log(f"  [AVISO] Nao encontrado: {fich}")
    log(f"  {ok}/{len(GEOSENSING_LAYERS)} camadas recarregadas")

def abrir_plugin_mergin():
    """Abre a interface do plugin Mergin Maps instalado no QGIS."""
    import qgis.utils
    if 'Mergin' not in qgis.utils.plugins:
        log("  [ERRO] Plugin Mergin Maps nao encontrado no QGIS")
        log("  Instala-o em: Plugins -> Gerir e Instalar Plugins -> Mergin Maps")
        return False

    plugin = qgis.utils.plugins['Mergin']

    # Tentar varios metodos conhecidos do plugin Mergin Maps
    aberto = False
    for metodo in ['configure']:
        if hasattr(plugin, metodo):
            try:
                getattr(plugin, metodo)()
                log(f"  [OK] Plugin Mergin Maps aberto via '{metodo}'")
                aberto = True
                break
            except Exception as e:
                log(f"  [AVISO] Metodo '{metodo}' falhou: {e}")
                continue

    if not aberto:
        # Listar metodos disponiveis para debug
        metodos = [m for m in dir(plugin) if not m.startswith('_')]
        log(f"  [INFO] Metodos disponiveis no plugin: {metodos}")
        log("  Abre manualmente: Plugins -> Mergin Maps")
        return False

    return True

# ─── GEOSENSING: PULL ─────────────────────────────────────
def geosensing_pull():
    """Faz sync do projeto Mergin Maps e recarrega as camadas no QGIS."""
    separador()
    log("GEOSENSING — Pull (servidor → QGIS)")
    separador()
    import qgis.utils
    if 'Mergin' not in qgis.utils.plugins:
        log("  [ERRO] Plugin Mergin Maps nao encontrado")
        return
    try:
        log("  A sincronizar com o servidor Mergin Maps...")
        qgis.utils.plugins['Mergin'].current_project_sync()
        log("  [OK] Sync concluido")
    except Exception as e:
        import traceback
        log(f"  [ERRO] Sync falhou: {e}\n{traceback.format_exc()}")
        return
    log("\n  A recarregar camadas...")
    recarregar_layers_geosensing()
    separador()
    log("PULL CONCLUIDO")
    separador()

# ─── GEOSENSING: PUSH ─────────────────────────────────────
def geosensing_push():
    """Cria projeto no Mergin Maps e faz upload dos ficheiros existentes."""
    separador()
    log("GEOSENSING — Push (QGIS → servidor)")
    separador()
    import qgis.utils
    if 'Mergin' not in qgis.utils.plugins:
        log("  [ERRO] Plugin Mergin Maps nao encontrado")
        return
    try:
        log("  A abrir assistente de criacao de projeto...")
        qgis.utils.plugins['Mergin'].create_new_project()
        log("  [OK] Assistente aberto — segue os passos para criar e fazer upload do projeto")
    except Exception as e:
        import traceback
        log(f"  [ERRO] {e}\n{traceback.format_exc()}")
    separador()

# ─── IMPORTACAO ───────────────────────────────────────────
def executar_importacao():
    import geopandas as gpd
    import osmnx as ox
    from shapely.geometry import box as shapely_box
    from qgis.core import (QgsVectorLayer, QgsRasterLayer, QgsProject)
    import warnings; warnings.filterwarnings('ignore')

    cidade       = combo_cidade.currentText()
    categoria    = combo_categoria.currentText()
    pasta_output = edit_output.text() or DEFAULT_PASTA_OUTPUT
    os.makedirs(pasta_output, exist_ok=True)
    bbox      = BBOXES[cidade]
    bbox_geom = shapely_box(bbox[0], bbox[1], bbox[2], bbox[3])

    separador()
    log(f"IMPORTACAO — {cidade}")
    separador()

    log("\n[1/4] Mapa base")
    uri = "type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D{x}%26y%3D{y}%26z%3D{z}&zmax=19&zmin=0"
    rl  = QgsRasterLayer(uri, "Google Satellite", "wms")
    if rl.isValid():
        QgsProject.instance().addMapLayer(rl)
        log("  [OK] Google Satellite")

    log(f"\n[2/4] POIs DGT")
    try:
        gdf = gpd.read_file(os.path.join(DEFAULT_PASTA_PORTUGAL, "pois.shp"))
        gdf = gdf.to_crs(epsg=4326)
        gdf = gdf[gdf.geometry.intersects(bbox_geom)].copy()
        gdf['fclass'] = gdf['fclass'].astype(str)
        log(f"  Total em {cidade}: {len(gdf)}")
        saida_base = os.path.join(pasta_output, f"pois_{cidade.lower()}_dgt.geojson")
        guardar_geojson(gdf, saida_base)
        gdf_cat = gdf[gdf['fclass'] == categoria].copy()
        log(f"  {categoria}: {len(gdf_cat)} POIs")
        if len(gdf_cat) > 0:
            saida_cat = os.path.join(pasta_output, f"pois_{categoria}_{cidade.lower()}.geojson")
            guardar_geojson(gdf_cat, saida_cat)
            adicionar_layer(saida_cat, f"POIs — {categoria} ({cidade})")
        else:
            log(f"  [AVISO] Nenhum POI para '{categoria}'")
    except Exception as e:
        import traceback
        log(f"  [ERRO] {e}\n{traceback.format_exc()}")

    # Edificios (shapefile externo)
    caminho_edif = edit_edificios.text().strip()
    if caminho_edif and os.path.exists(caminho_edif):
        log(f"\n[+] Edificios")
        try:
            gdf = gpd.read_file(caminho_edif)
            gdf = gdf.to_crs(epsg=4326)
            gdf = gdf[gdf.geometry.intersects(bbox_geom)].copy()
            saida = os.path.join(pasta_output, f"edificios_{cidade.lower()}.geojson")
            guardar_geojson(gdf, saida)
            adicionar_layer(saida, f"Edificios — {cidade}")
        except Exception as e:
            log(f"  [ERRO] {e}")

    log(f"\n[3/4] Estradas DGT")
    try:
        gdf = gpd.read_file(os.path.join(DEFAULT_PASTA_PORTUGAL, "roads.shp"))
        gdf = gdf.to_crs(epsg=4326)
        gdf = gdf[gdf.geometry.intersects(bbox_geom)].copy()
        saida = os.path.join(pasta_output, f"estradas_{cidade.lower()}_dgt.geojson")
        guardar_geojson(gdf, saida)
        adicionar_layer(saida, f"Estradas — {cidade}")
    except Exception as e:
        log(f"  [ERRO] {e}")

    log(f"\n[4/4] Paragens OSMnx")
    try:
        paragens = ox.features_from_place(f"{cidade}, Portugal", tags={"highway": "bus_stop"})
        paragens = paragens[paragens.geometry.geom_type == 'Point'].copy()
        saida    = os.path.join(pasta_output, f"paragens_{cidade.lower()}.geojson")
        guardar_geojson(paragens, saida)
        adicionar_layer(saida, f"Paragens — {cidade}")
    except Exception as e:
        log(f"  [ERRO] {e}")

    log(f"\n[+] GeoSensing layers")
    try:
        from qgis.core import (QgsVectorLayer, QgsField, QgsProject,
                                QgsVectorFileWriter, QgsCoordinateReferenceSystem)
        from qgis.PyQt.QtCore import QVariant
        pasta_proj = edit_output.text() or DEFAULT_PASTA_OUTPUT

        for nome_layer, nome_fich in GEOSENSING_LAYERS:
            caminho = os.path.join(pasta_proj, nome_fich)

            # Remover layer existente do QGIS
            for lyr in list(QgsProject.instance().mapLayers().values()):
                if lyr.name() == nome_layer:
                    QgsProject.instance().removeMapLayer(lyr)
            time.sleep(0.2)

            # Apagar ficheiro antigo
            if os.path.exists(caminho):
                os.remove(caminho)

            # Criar layer em memoria com campos
            lyr_mem = QgsVectorLayer("Point?crs=EPSG:4326", nome_layer, "memory")
            pr = lyr_mem.dataProvider()
            pr.addAttributes([
                QgsField("titulo",    QVariant.String),
                QgsField("descricao", QVariant.String),
                QgsField("data",      QVariant.String),
                QgsField("autor",     QVariant.String),
            ])
            lyr_mem.updateFields()

            # Guardar como GPKG
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.fileEncoding = "UTF-8"
            options.layerName = nome_layer
            QgsVectorFileWriter.writeAsVectorFormatV3(
                lyr_mem, caminho,
                QgsProject.instance().transformContext(),
                options
            )

            # Carregar do disco e ativar modo de edicao
            uri = f"{caminho}|layername={nome_layer}"
            lyr = QgsVectorLayer(uri, nome_layer, "ogr")
            if lyr.isValid():
                QgsProject.instance().addMapLayer(lyr)
                log(f"  [OK] {nome_layer}")
            else:
                log(f"  [ERRO] Layer invalido: {caminho}")
    except Exception as e:
        import traceback
        log(f"  [ERRO] {e}\n{traceback.format_exc()}")

    separador()
    log("IMPORTACAO CONCLUIDA")
    separador()

# ─── ANALISE ──────────────────────────────────────────────
def executar_analise():
    import geopandas as gpd
    import numpy as np
    import requests, json
    from shapely.geometry import Point
    from sklearn.cluster import DBSCAN
    from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsProject
    import processing, warnings; warnings.filterwarnings('ignore')

    cidade        = combo_cidade.currentText()
    categoria     = combo_categoria.currentText()
    pasta_output  = edit_output.text() or DEFAULT_PASTA_OUTPUT
    transporte    = combo_transporte.currentText()
    rota_pref     = combo_rota_pref.currentText()
    perfil_ors    = ORS_PERFIS[transporte]
    top_n         = spin_top_clusters.value()
    buffer_m      = spin_buffer_m.value()
    dbscan_min    = spin_dbscan_min.value()
    dbscan_eps_km = dspin_dbscan_eps.value()
    heatmap_raio  = dspin_heatmap_raio.value()
    iso_dist1     = spin_iso1.value()
    iso_dist2     = spin_iso2.value()

    try:
        origem_lat = float(edit_origem_lat.text())
        origem_lon = float(edit_origem_lon.text())
    except:
        log("[ERRO] Coordenadas de origem invalidas!")
        return

    dest_lat, dest_lon = obter_destino()
    usar_destino_fixo  = (dest_lat is not None and dest_lon is not None)

    separador()
    log(f"ANALISE — {categoria} em {cidade}")
    log(f"  Buffer:{buffer_m}m | DBSCAN eps:{dbscan_eps_km}km min:{dbscan_min} | Heatmap:{heatmap_raio} | Iso:{iso_dist1}m/{iso_dist2}m")
    separador()

    # ── 1. POIs ──────────────────────────────────────────
    log("\n[1/4] POIs")
    try:
        saida_base = os.path.join(pasta_output, f"pois_{cidade.lower()}_dgt.geojson")
        if not os.path.exists(saida_base):
            log("  [ERRO] Ficheiro base nao encontrado — corre primeiro a Importacao")
            return
        gdf           = gpd.read_file(saida_base)
        gdf['fclass'] = gdf['fclass'].astype(str)
        pois_cat      = gdf[gdf['fclass'] == categoria].copy()
        log(f"  {categoria} em {cidade}: {len(pois_cat)}")
        if len(pois_cat) == 0:
            log(f"  [ERRO] Nenhum POI para '{categoria}'")
            return
        origem_gdf = gpd.GeoDataFrame(geometry=[Point(origem_lon, origem_lat)], crs="EPSG:4326")
        buffer     = origem_gdf.to_crs(epsg=3763).buffer(buffer_m).to_crs(epsg=4326).unary_union
        pois_buf   = pois_cat[pois_cat.geometry.within(buffer)].copy()
        log(f"  Raio {buffer_m}m: {len(pois_buf)} POIs")
        saida_cat = os.path.join(pasta_output, f"pois_{categoria}_{cidade.lower()}.geojson")
        guardar_geojson(pois_cat, saida_cat)
        adicionar_layer(saida_cat, f"POIs — {categoria} ({cidade})")
        saida_buf = os.path.join(pasta_output, f"pois_{categoria}_{cidade.lower()}_buffer.geojson")
        guardar_geojson(pois_buf, saida_buf)
        adicionar_layer(saida_buf, f"POIs — {categoria} {buffer_m}m")
    except Exception as e:
        import traceback
        log(f"  [ERRO] {e}\n{traceback.format_exc()}")
        return

    # ── 2. Heatmap ───────────────────────────────────────
    log("\n[2/4] Heatmap")
    try:
        layer_pois      = QgsProject.instance().mapLayersByName(f"POIs — {categoria} ({cidade})")[0]
        caminho_heatmap = os.path.join(pasta_output, f"heatmap_{categoria}_{cidade.lower()}.tif")
        if os.path.exists(caminho_heatmap): os.remove(caminho_heatmap)
        processing.run("qgis:heatmapkerneldensityestimation", {
            'INPUT': layer_pois, 'RADIUS': heatmap_raio,
            'PIXEL_SIZE': 0.0002, 'KERNEL': 0, 'OUTPUT': caminho_heatmap
        })
        lyr_h = QgsRasterLayer(caminho_heatmap, f"Heatmap — {categoria}")
        QgsProject.instance().addMapLayer(lyr_h)
        aplicar_simbologia_heatmap(lyr_h)
        log(f"  [OK] Heatmap gerado (raio {heatmap_raio})")
    except Exception as e:
        log(f"  [ERRO] {e}")

    # ── 3. DBSCAN ────────────────────────────────────────
    log(f"\n[3/4] DBSCAN (eps={dbscan_eps_km}km, min={dbscan_min}, top {top_n})")
    lon_c, lat_c = dest_lon, dest_lat
    try:
        coords     = np.array([[g.y, g.x] for g in pois_cat.geometry])
        coords_rad = np.radians(coords)
        db         = DBSCAN(eps=dbscan_eps_km/6371.0, min_samples=dbscan_min,
                            algorithm='ball_tree', metric='haversine').fit(coords_rad)
        labels     = db.labels_
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        log(f"  Clusters: {n_clusters} | Ruido: {list(labels).count(-1)}")
        pois_cl            = pois_cat.copy()
        pois_cl['cluster'] = labels.astype(str)
        saida_cl = os.path.join(pasta_output, f"pois_{categoria}_clusters.geojson")
        guardar_geojson(pois_cl, saida_cl)
        adicionar_layer(saida_cl, f"DBSCAN — {categoria}")
        contagens    = {cl: list(labels).count(cl) for cl in set(labels) if cl >= 0}
        top_clusters = sorted(contagens, key=contagens.get, reverse=True)[:top_n]
        log(f"  Top {top_n} clusters:")
        centroides = []
        for i, cl in enumerate(top_clusters):
            mask     = labels == cl
            lat_c_db = coords[mask, 0].mean()
            lon_c_db = coords[mask, 1].mean()
            n_pois   = contagens[cl]
            log(f"    #{i+1} Cluster {cl}: {n_pois} POIs @ {lat_c_db:.4f}, {lon_c_db:.4f}")
            centroides.append({"rank": i+1, "cluster": cl, "n_pois": n_pois,
                               "lat": lat_c_db, "lon": lon_c_db})
        if centroides:
            gdf_c = gpd.GeoDataFrame(
                [{"rank": c["rank"], "cluster": c["cluster"], "n_pois": c["n_pois"]}
                 for c in centroides],
                geometry=[Point(c["lon"], c["lat"]) for c in centroides],
                crs="EPSG:4326"
            )
            saida_c = os.path.join(pasta_output, f"centroides_{cidade.lower()}.geojson")
            guardar_geojson(gdf_c, saida_c)
            adicionar_layer(saida_c, f"Centroides Top {top_n}")
            if not usar_destino_fixo:
                lat_c = centroides[0]["lat"]
                lon_c = centroides[0]["lon"]
                log(f"  Destino automatico: cluster #{centroides[0]['cluster']} ({centroides[0]['n_pois']} POIs)")
    except Exception as e:
        import traceback
        log(f"  [ERRO] {e}\n{traceback.format_exc()}")
        if not usar_destino_fixo:
            return

    # ── 4. Isocronas ─────────────────────────────────────
    log("\n[+] Isocronas paragens")
    try:
        gdf_par = gpd.read_file(os.path.join(pasta_output, f"paragens_{cidade.lower()}.geojson")).to_crs(epsg=3763)
        for dist, cor, opac in [
            (iso_dist1, '#a8d1f0', 0.3),
            (iso_dist2, '#2171b5', 0.4),
        ]:
            saida_i = os.path.join(pasta_output, f"iso_{dist}m_{cidade.lower()}.geojson")
            buf     = gpd.GeoDataFrame(geometry=[gdf_par.buffer(dist).unary_union], crs="EPSG:3763").to_crs(epsg=4326)
            guardar_geojson(buf, saida_i)
            lyr = adicionar_layer(saida_i, f"Isocronas {dist}m")
            if lyr:
                aplicar_simbologia_vetor(lyr, cor, opac)
    except Exception as e:
        log(f"  [ERRO] {e}")

    separador()
    log("ANALISE CONCLUIDA")
    separador()

# ─── ROTA ORS ────────────────────────────────────────────
def calcular_rota():
    import requests, json, os
    from qgis.core import QgsProject

    cidade       = combo_cidade.currentText()
    pasta_output = edit_output.text() or DEFAULT_PASTA_OUTPUT
    transporte   = combo_transporte.currentText()
    rota_pref    = combo_rota_pref.currentText()
    perfil_ors   = ORS_PERFIS[transporte]
    pref_ors     = "shortest" if rota_pref == "Mais curta" else "fastest"
    if perfil_ors != "driving-car" and pref_ors == "fastest":
        pref_ors = "recommended"

    try:
        origem_lat = float(edit_origem_lat.text())
        origem_lon = float(edit_origem_lon.text())
    except:
        log("[ERRO] Coordenadas de origem invalidas!")
        return

    # Obter destino
    dest_lat, dest_lon = obter_destino()

    # Se nao ha destino manual, tentar usar centroide do ultimo DBSCAN
    if dest_lat is None or dest_lon is None:
        import geopandas as gpd
        saida_c = os.path.join(pasta_output, f"centroides_{cidade.lower()}.geojson")
        if os.path.exists(saida_c):
            gdf_c    = gpd.read_file(saida_c)
            dest_lat = gdf_c.geometry.iloc[0].y
            dest_lon = gdf_c.geometry.iloc[0].x
            log(f"  Destino: centroide DBSCAN ({dest_lat:.4f}, {dest_lon:.4f})")
        else:
            log("[ERRO] Sem destino definido e sem centroide DBSCAN — define um destino primeiro")
            return

    separador()
    log(f"ROTA — {transporte} / {rota_pref}")
    log(f"  Origem:  {origem_lat:.5f}, {origem_lon:.5f}")
    log(f"  Destino: {dest_lat:.5f}, {dest_lon:.5f}")
    separador()

    try:
        url     = f"https://api.openrouteservice.org/v2/directions/{perfil_ors}/geojson"
        headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
        body    = {"coordinates": [[origem_lon, origem_lat], [dest_lon, dest_lat]], "preference": pref_ors}
        r       = requests.post(url, json=body, headers=headers, timeout=15)

        if r.status_code == 200:
            rota = r.json()
            dist = rota["features"][0]["properties"]["summary"]["distance"]
            dur  = rota["features"][0]["properties"]["summary"]["duration"]
            nome_rota = f"Rota — {transporte} / {rota_pref} ({dist:.0f}m, {dur/60:.1f}min)"
            saida_r   = os.path.join(pasta_output, f"rota_{perfil_ors}_{pref_ors}.geojson")
            if os.path.exists(saida_r): os.remove(saida_r)
            with open(saida_r, "w") as f: json.dump(rota, f)
            adicionar_layer(saida_r, nome_rota)
            log(f"  [OK] {dist:.0f}m — {dur/60:.1f} min")
        else:
            log(f"  [ERRO ORS] {r.status_code}: {r.text[:300]}")
    except Exception as e:
        import traceback
        log(f"  [ERRO] {e}\n{traceback.format_exc()}")

    separador()

# ─── GUARDAR PROJETO ─────────────────────────────────────
def guardar_projeto():
    from qgis.core import QgsProject
    pasta = QFileDialog.getExistingDirectory(None, "Selecionar pasta para guardar projeto", edit_output.text() or DEFAULT_PASTA_OUTPUT)
    if not pasta:
        log("  Guardar projeto cancelado")
        return
    separador()
    log("GUARDAR PROJETO")
    separador()
    try:
        caminho_qgz = os.path.join(pasta, "GeoSensing.qgz")
        QgsProject.instance().setFileName(caminho_qgz)
        QgsProject.instance().write()
        log(f"  [OK] Projeto guardado: {caminho_qgz}")
    except Exception as e:
        import traceback
        log(f"  [ERRO] {e}\n{traceback.format_exc()}")
    separador()

# ─── INTERFACE ────────────────────────────────────────────
def _sel_shp():
    from qgis.PyQt.QtWidgets import QFileDialog
    path, _ = QFileDialog.getOpenFileName(None, "Selecionar shapefile de edificios", "", "Shapefiles (*.shp)")
    if path:
        edit_edificios.setText(path)

def newwindow():
    widget = QDialog(iface.mainWindow()) if iface else QDialog()
    widget.setWindowTitle("GeoSensing & Community Hub")
    widget.setMinimumWidth(560)
    widget.setStyleSheet("""
        QDialog      { background:#2b2b2b; color:#eeeeee; }
        QGroupBox    { border:1px solid #444; border-radius:5px; margin-top:8px; color:#aaaaaa; font-size:11px; }
        QGroupBox::title { subcontrol-origin:margin; left:8px; padding:0 4px; }
        QLabel       { color:#dddddd; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background:#3c3c3c; border:1px solid #555; border-radius:3px;
            color:#eeeeee; padding:3px 6px; }
        QComboBox::drop-down { border:none; }
        QRadioButton { color:#dddddd; }
        QTextEdit    { background:#1e1e1e; color:#b0ffb0; border:1px solid #444;
                       font-family:Consolas,monospace; font-size:11px; }
        QPushButton  { border-radius:4px; padding:7px; font-weight:bold; color:white; }
    """)

    main = QVBoxLayout()
    main.setSpacing(8)
    main.setContentsMargins(10, 10, 10, 10)

    # ── Dados ─────────────────────────────────────────────
    g1 = QGroupBox("Dados"); l1 = QVBoxLayout(); l1.setSpacing(5)
    r1 = QHBoxLayout()
    r1.addWidget(QLabel("Cidade:"))
    combo_cidade.clear(); combo_cidade.addItems(["Coimbra", "Porto", "Lisboa"])
    r1.addWidget(combo_cidade, 2); r1.addSpacing(8)
    r1.addWidget(QLabel("Categoria POI:"))
    combo_categoria.clear(); combo_categoria.addItems(CATEGORIAS_CONFIAVEIS)
    r1.addWidget(combo_categoria, 2); l1.addLayout(r1)
    r2 = QHBoxLayout()
    r2.addWidget(QLabel("Output:"))
    edit_output.setText(DEFAULT_PASTA_OUTPUT)
    btn_out = QPushButton("…"); btn_out.setFixedWidth(28)
    btn_out.clicked.connect(lambda: selecionar_pasta(edit_output, DEFAULT_PASTA_OUTPUT))
    r2.addWidget(edit_output, 4); r2.addWidget(btn_out); l1.addLayout(r2)

    r3 = QHBoxLayout()
    r3.addWidget(QLabel("Edificios (.shp):"))
    edit_edificios.setPlaceholderText("ex: C:\\caminho\\edificios.shp")
    btn_edif = QPushButton("…"); btn_edif.setFixedWidth(28)
    btn_edif.clicked.connect(lambda: _sel_shp())
    r3.addWidget(edit_edificios, 4); r3.addWidget(btn_edif); l1.addLayout(r3)
    g1.setLayout(l1); main.addWidget(g1)

    # ── Origem ────────────────────────────────────────────
    g2 = QGroupBox("Origem  (pre-definida: ISEC Coimbra)"); l2 = QHBoxLayout()
    l2.addWidget(QLabel("Lat:")); edit_origem_lat.setText(ISEC_LAT); l2.addWidget(edit_origem_lat)
    l2.addSpacing(8)
    l2.addWidget(QLabel("Lon:")); edit_origem_lon.setText(ISEC_LON); l2.addWidget(edit_origem_lon)
    g2.setLayout(l2); main.addWidget(g2)

    # ── Destino ───────────────────────────────────────────
    g3 = QGroupBox("Destino"); l3 = QVBoxLayout(); l3.setSpacing(5)
    rr = QHBoxLayout()
    radio_coords.setChecked(True)
    rg = QButtonGroup(widget); rg.addButton(radio_coords); rg.addButton(radio_texto)
    rr.addWidget(radio_coords); rr.addWidget(radio_texto); rr.addStretch(); l3.addLayout(rr)
    pag1 = QWidget(); pp1 = QHBoxLayout(pag1); pp1.setContentsMargins(0,0,0,0)
    pp1.addWidget(QLabel("Lat:"))
    edit_dest_lat.setPlaceholderText("ex: 40.208538"); pp1.addWidget(edit_dest_lat)
    pp1.addSpacing(8); pp1.addWidget(QLabel("Lon:"))
    edit_dest_lon.setPlaceholderText("ex: -8.419558"); pp1.addWidget(edit_dest_lon)
    pag2 = QWidget(); pp2 = QHBoxLayout(pag2); pp2.setContentsMargins(0,0,0,0)
    edit_dest_texto.setPlaceholderText("ex: Hospital da Universidade de Coimbra")
    pp2.addWidget(edit_dest_texto)
    stack_destino.addWidget(pag1); stack_destino.addWidget(pag2)
    radio_coords.toggled.connect(lambda c: stack_destino.setCurrentIndex(0) if c else None)
    radio_texto.toggled.connect( lambda c: stack_destino.setCurrentIndex(1) if c else None)
    l3.addWidget(stack_destino)
    lh = QLabel("Vazio = usa centroide DBSCAN como destino")
    lh.setStyleSheet("color:#888; font-size:10px;"); l3.addWidget(lh)
    g3.setLayout(l3); main.addWidget(g3)

    # ── Rota ──────────────────────────────────────────────
    g4 = QGroupBox("Rota"); l4 = QHBoxLayout(); l4.setSpacing(10)
    l4.addWidget(QLabel("Transporte:"))
    combo_transporte.clear(); combo_transporte.addItems(list(ORS_PERFIS.keys()))
    l4.addWidget(combo_transporte, 2)
    l4.addWidget(QLabel("Preferencia:"))
    combo_rota_pref.clear(); combo_rota_pref.addItems(["Mais curta", "Mais rapida"])
    l4.addWidget(combo_rota_pref, 2)
    g4.setLayout(l4); main.addWidget(g4)

    # ── DBSCAN ────────────────────────────────────────────
    g5 = QGroupBox("DBSCAN"); l5 = QHBoxLayout(); l5.setSpacing(10)
    l5.addWidget(QLabel("Top N clusters:"))
    spin_top_clusters.setRange(1, 10); spin_top_clusters.setValue(3); spin_top_clusters.setFixedWidth(50)
    l5.addWidget(spin_top_clusters); l5.addSpacing(8)
    l5.addWidget(QLabel("Eps (km):"))
    dspin_dbscan_eps.setRange(0.05, 10.0); dspin_dbscan_eps.setSingleStep(0.05)
    dspin_dbscan_eps.setValue(0.30); dspin_dbscan_eps.setFixedWidth(65)
    l5.addWidget(dspin_dbscan_eps); l5.addSpacing(8)
    l5.addWidget(QLabel("Min pts:"))
    spin_dbscan_min.setRange(2, 20); spin_dbscan_min.setValue(3); spin_dbscan_min.setFixedWidth(50)
    l5.addWidget(spin_dbscan_min); l5.addStretch()
    g5.setLayout(l5); main.addWidget(g5)

    # ── Parametros ────────────────────────────────────────
    g6 = QGroupBox("Parametros"); l6 = QHBoxLayout(); l6.setSpacing(10)
    l6.addWidget(QLabel("Buffer (m):"))
    spin_buffer_m.setRange(100, 10000); spin_buffer_m.setSingleStep(100)
    spin_buffer_m.setValue(1000); spin_buffer_m.setFixedWidth(70)
    l6.addWidget(spin_buffer_m); l6.addSpacing(8)
    l6.addWidget(QLabel("Heatmap raio:"))
    dspin_heatmap_raio.setRange(0.001, 0.05); dspin_heatmap_raio.setSingleStep(0.001)
    dspin_heatmap_raio.setDecimals(3); dspin_heatmap_raio.setValue(0.005); dspin_heatmap_raio.setFixedWidth(70)
    l6.addWidget(dspin_heatmap_raio); l6.addSpacing(8)
    l6.addWidget(QLabel("Isocronas (m):"))
    spin_iso1.setRange(50, 2000); spin_iso1.setSingleStep(50); spin_iso1.setValue(400); spin_iso1.setFixedWidth(60)
    l6.addWidget(spin_iso1); l6.addWidget(QLabel("/"))
    spin_iso2.setRange(50, 2000); spin_iso2.setSingleStep(50); spin_iso2.setValue(200); spin_iso2.setFixedWidth(60)
    l6.addWidget(spin_iso2); l6.addStretch()
    g6.setLayout(l6); main.addWidget(g6)

    # ── GeoSensing ────────────────────────────────────────
    g7 = QGroupBox("GeoSensing — Mergin Maps"); l7 = QVBoxLayout(); l7.setSpacing(6)

    # Pasta projeto = pasta output (mesmo campo)
    lbl_proj = QLabel("Pasta projeto Mergin = pasta Output definida em cima.")
    lbl_proj.setStyleSheet("color:#888; font-size:10px;")
    l7.addWidget(lbl_proj)

    # Botoes Pull / Push
    rb_gs = QHBoxLayout(); rb_gs.setSpacing(6)
    b_pull = QPushButton("↓  Pull  —  Receber do servidor")
    b_pull.setStyleSheet("background:#1a6b3c;"); b_pull.clicked.connect(geosensing_pull)
    b_push = QPushButton("↑  Push  —  Enviar para servidor")
    b_push.setStyleSheet("background:#7a3c1a;"); b_push.clicked.connect(geosensing_push)
    rb_gs.addWidget(b_pull); rb_gs.addWidget(b_push)
    l7.addLayout(rb_gs)

    lbl_gs = QLabel("Pull e Push abrem o plugin Mergin Maps — faz Sync lá e fecha para recarregar as camadas.")
    lbl_gs.setStyleSheet("color:#888; font-size:10px;"); l7.addWidget(lbl_gs)
    g7.setLayout(l7); main.addWidget(g7)

    # ── Botoes principais ─────────────────────────────────
    rb = QHBoxLayout(); rb.setSpacing(6)
    b1 = QPushButton("1. Importar Dados")
    b1.setStyleSheet("background:#2e7abf;"); b1.clicked.connect(executar_importacao)
    b2 = QPushButton("2. Executar Analise")
    b2.setStyleSheet("background:#1a5f9e;"); b2.clicked.connect(executar_analise)
    rb.addWidget(b1); rb.addWidget(b2)
    main.addLayout(rb)

    b_rota = QPushButton("3. Calcular Rota  (ORS)")
    b_rota.setStyleSheet("background:#6a3c9e;"); b_rota.clicked.connect(calcular_rota)
    main.addWidget(b_rota)

    b_save = QPushButton("4. Guardar Projeto  (.qgz)")
    b_save.setStyleSheet("background:#7a5c1a;"); b_save.clicked.connect(guardar_projeto)
    main.addWidget(b_save)

    # ── Log ───────────────────────────────────────────────
    g8 = QGroupBox("Log"); l8 = QVBoxLayout()
    log_text.setReadOnly(True); log_text.setMinimumHeight(150)
    log_text.setPlainText("Pronto. Clica em '1. Importar Dados' para comecar.")
    l8.addWidget(log_text); g8.setLayout(l8); main.addWidget(g8)

    widget.setLayout(main)
    widget.show()
    if not iface:
        sys.exit(app.exec_())

if __name__ == '__main__':
    newwindow()
else:
    newwindow()