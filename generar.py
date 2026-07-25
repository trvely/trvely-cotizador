#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Motor unico del Cotizador Trvely (cotizador.trvely.com.co).

Regenera el snapshot (productos: precio por fecha + vuelos + inclusiones + tour + galeria + experiencias)
y arma index.html desde template.html + assets/. Reconoce solo lo que ya existe: si entra una galeria,
una experiencia o un producto nuevo, aparece en la siguiente corrida.

Modos:
  --full   : re-extrae TODO desde el MOTOR (PROD, requiere PGPROD_PW) + galerias + experiencias.
             Lo corre el corte en la nube (o manual) para el refresco diario de precios/productos.
  --remap  : CONSERVA los precios del snapshot commiteado y solo refresca galeria/experiencias desde el
             repo de galerias (SIN llaves de PROD). Lo corre el robot de la nube cuando entra una
             galeria o experiencia nueva -> republica el cotizador solo.
  (sin arg): solo re-arma index.html desde el snapshot commiteado (build).

Fuentes: galerias = GALERIAS_DIR (default el repo local; en la Action, el clon de trvely-galerias).
PROD local: setear PGHOST_OVERRIDE / PGPORT_OVERRIDE / PGUSER_OVERRIDE para el host directo.
"""
import os, re, json, glob, sys, datetime

REPO = os.path.dirname(os.path.abspath(__file__))
GALERIAS_DIR = os.environ.get("GALERIAS_DIR", r"C:\Users\jonat\trvely-galerias")
SNAP = os.path.join(REPO, "snapshot_asesor.json")
TPL  = os.path.join(REPO, "template.html")
OUT  = os.path.join(REPO, "index.html")
PROD_REF = "unohlejndahgypsdtsgm"
PT_ID = "a1aaabce-b510-4277-b412-904027d13227"
DEST_MAP = {'SMR':'Santa Marta','CTG':'Cartagena','COV':'Coveñas','ADZ':'San Andrés','TLU':'Tolú',
            'LET':'Leticia','PUJ':'Punta Cana','RCH':'Riohacha','SDQ':'Boca Chica','JDL':'Juan Dolio','MDE':'Medellín'}
EXP_FALLBACK = {'cartagena','santa-marta','medellin','leticia'}
DSLUG = {'Santa Marta':'santa-marta','Cartagena':'cartagena','Coveñas':'covenas','San Andrés':'san-andres',
  'Tolú':'tolu','Boca Chica':'boca-chica','Leticia':'leticia','Punta Cana':'punta-cana','Riohacha':'riohacha',
  'Juan Dolio':'juan-dolio','Medellín':'medellin'}

def norm(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())
def hhmm(t): return t.strftime('%H:%M') if t else None

def galerias_map():
    gal = {}
    for m in glob.glob(os.path.join(GALERIAS_DIR, '*', 'meta.json')):
        try:
            d = json.load(open(m, encoding='utf-8')); gal[norm(d.get('titulo'))] = d.get('slug')
        except Exception:
            pass
    return gal

def exp_vivas():
    p = os.path.join(GALERIAS_DIR, '.vitrina', 'experiencias_respaldo.json')
    if os.path.exists(p):
        try:
            return {e['slug'] for e in json.load(open(p, encoding='utf-8')) if e.get('vivo')}
        except Exception:
            pass
    return set(EXP_FALLBACK)

def alias_map():
    """Alias manual hotel->slug de galeria, para nombres que no calzan exacto
    (la medicion propone, el alias dispone; patron portadas_manual de la Vitrina)."""
    p = os.path.join(REPO, 'alias_hoteles.json')
    if os.path.exists(p):
        try:
            return {norm(k): v for k, v in json.load(open(p, encoding='utf-8')).items()}
        except Exception:
            pass
    return {}

def mapear(prods, gal, exp, alias=None):
    """Anota galeria + experiencias en cada producto (reconoce las nuevas)."""
    alias = alias or {}
    gal_by_slug = {norm(v): v for v in gal.values() if v}
    def slug_hotel(nombre):
        k = norm(nombre)
        if k in alias: return alias[k]          # alias manual gana
        if k in gal: return gal[k]
        if k in gal_by_slug: return gal_by_slug[k]
        for gk, gv in gal.items():
            if gk and len(gk) > 5 and (gk in k or k in gk): return gv
        return None
    con_g = con_e = 0
    for p in prods:
        s = slug_hotel(p['hotel'])
        p['galeria'] = f"https://galerias.trvely.com.co/{s}/" if s else None
        ds = DSLUG.get(p['destino'])
        p['experiencias'] = f"https://experiencias.trvely.com.co/{ds}/" if ds in exp else None
        con_g += bool(p['galeria']); con_e += bool(p['experiencias'])
    return con_g, con_e

QUERY_FECHAS = """
select split_part(pt.codigo,'-',1) destino_cod, c.hotel, c.plan_alimentacion, c.tipo_habitacion, pt.noches,
  fe.fecha_ida, fe.fecha_regreso,
  coalesce(c.valor_tiquete_total_banco,0), coalesce(c.valor_alojamiento,0), coalesce(c.valor_tours,0),
  coalesce(c.valor_traslado,0), coalesce(c.valor_asistencias,0), c.precio_venta_p_p, pt.codigo,
  fe.aerolinea_ida, fe.hora_salida_ida, fe.hora_llegada_ida,
  fe.aerolinea_regreso, fe.hora_salida_regreso, fe.hora_llegada_regreso,
  fe.tiene_escalas_ida, fe.tiene_escalas_regreso
from paquetes_turisticos pt
cross join lateral (
  select distinct f.fecha_ida, f.fecha_regreso, f.aerolinea_ida, f.hora_salida_ida, f.hora_llegada_ida,
    f.aerolinea_regreso, f.hora_salida_regreso, f.hora_llegada_regreso, f.tiene_escalas_ida, f.tiene_escalas_regreso
  from paquete_bancos_itinerario pbi
  join bancos_itinerario b on b.id=pbi.banco_itinerario_id
  join banco_itinerario_fechas f on f.banco_itinerario_id=pbi.banco_itinerario_id
  where pbi.paquete_id=pt.id and b.estado_operativo='COMPLETO_OPERATIVO' and b.activo and f.activo
    and upper(coalesce(f.estado_tiquete_fecha,''))='VIGENTE'
    and (f.fecha_regreso-f.fecha_ida)=pt.noches and f.valor_tiquete_real_total is not null
) fe
cross join lateral fn_costeo_paquete_turistico(pt.codigo, fe.fecha_ida, fe.fecha_regreso) c
where pt.tipo_producto_id=%s and pt.activo and upper(c.acomodacion)='DOBLE' and c.precio_venta_p_p is not null
order by split_part(pt.codigo,'-',1), c.hotel, pt.codigo, fe.fecha_ida
"""
QUERY_SERV = """
select pt.codigo, sc.tipo_servicio, sc.nombre
from paquetes_turisticos pt
join paquete_servicios ps on ps.paquete_id=pt.id and ps.es_base=true and ps.incluido=true
join servicios_catalogo sc on sc.id=ps.servicio_id
where pt.tipo_producto_id=%s and pt.activo
order by pt.codigo, ps.orden
"""

def extraer_prod():
    import psycopg2
    from collections import OrderedDict
    pw = os.environ["PGPROD_PW"]
    host = os.environ.get("PGHOST_OVERRIDE", "aws-0-us-west-2.pooler.supabase.com")
    port = int(os.environ.get("PGPORT_OVERRIDE", "6543"))
    user = os.environ.get("PGUSER_OVERRIDE", f"postgres.{PROD_REF}")
    conn = psycopg2.connect(host=host, port=port, user=user, password=pw, dbname="postgres", connect_timeout=25)
    cur = conn.cursor()
    cur.execute(QUERY_FECHAS, (PT_ID,)); rows = cur.fetchall()
    cur.execute(QUERY_SERV, (PT_ID,))
    serv = {}
    for cod, tipo, nombre in cur.fetchall():
        serv.setdefault(cod, {}).setdefault(tipo, []).append(nombre.strip())
    conn.close()
    prods = OrderedDict()
    for r in rows:
        (dcod, hotel, alim, hab, noches, ida, reg, tiq, aloj, tours, trasl, asist, precio, cod,
         ai, hsi, hli, ar, hsr, hlr, ei, er) = r
        p = prods.get(cod)
        if p is None:
            p = prods[cod] = dict(destino=DEST_MAP.get(dcod, dcod), hotel=hotel, alimentacion=alim, habitacion=hab,
                noches=noches, codigo=cod, fechas=[],
                incluye=dict(tiquete=tiq>0, alojamiento=aloj>0, tours=tours>0, traslado=trasl>0, asistencia=asist>0))
        vuelo = {"ai":ai,"si":hhmm(hsi),"li":hhmm(hli),"ar":ar,"sr":hhmm(hsr),"lr":hhmm(hlr),"ei":bool(ei),"er":bool(er)}
        if not any(f[0]==str(ida) for f in p["fechas"]):
            p["fechas"].append([str(ida), str(reg), int(round(precio)), vuelo])
    lista = []
    for cod, p in prods.items():
        s = serv.get(cod, {}); p["tours_incluidos"] = s.get('TOUR', []) + s.get('COMBO', []); p["traslados"] = s.get('TRASLADO', [])
        pr = [f[2] for f in p["fechas"]]; p["desde"], p["hasta"], p["n_fechas"] = min(pr), max(pr), len(pr)
        lista.append(p)
    return lista

def build_index(data):
    tpl = open(TPL, encoding="utf-8").read()
    html = (tpl.replace('__EXTENDA__', 'assets/extenda.ttf').replace('__WHITESTAR__', 'assets/whitestar.otf')
            .replace('__LOGO__', 'assets/logo-beige.png').replace('__TRIANA__', 'assets/triana.webp')
            .replace('__CIELO__', 'assets/cielo-footer.webp').replace('__DATA__', json.dumps(data, ensure_ascii=False)))
    open(OUT, "w", encoding="utf-8").write(html)

def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    gal, exp, alias = galerias_map(), exp_vivas(), alias_map()
    if modo == "--full":
        prods = extraer_prod()
        cg, ce = mapear(prods, gal, exp, alias)
        data = dict(generado=datetime.date.today().isoformat(), acomodacion="doble", productos=prods)
        json.dump(data, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        data = json.load(open(SNAP, encoding="utf-8"))
        if modo == "--remap":
            cg, ce = mapear(data["productos"], gal, exp, alias)
            json.dump(data, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        else:
            cg = sum(1 for p in data["productos"] if p.get("galeria"))
            ce = sum(1 for p in data["productos"] if p.get("experiencias"))
    build_index(data)
    print(f"OK [{modo or 'build'}] · {len(data['productos'])} productos · {cg} con galeria · {ce} con experiencias "
          f"· {len(gal)} galerias vistas · generado {data['generado']}")

if __name__ == "__main__":
    main()
