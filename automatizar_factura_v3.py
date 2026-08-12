"""
Automatización — Ingreso de Factura de Compra en Logi Stock (VERSIÓN 3)
==========================================================================
Video: "Cómo diseñé este proceso automatizado sin mover el mouse"

Fix vs. v2:
    La tabla de líneas (cantidad, precio, lote, vto. lote) se re-renderiza
    ENTERA cada vez que un campo dispara "change" (así está programada la
    app: onchange="...;renderLineasComprobanteTable()"). Guardar el elemento
    una sola vez y reusarlo rompe todo con un StaleElementReferenceException
    en cuanto el DOM se reconstruye. Ahora cada campo de la fila se vuelve
    a buscar en el DOM justo antes de tocarlo, y se dispara el evento
    "change" a mano apenas se termina de tipear (en vez de dejar que lo
    dispare el click al campo siguiente, que es lo que fallaba antes).

Requisitos:
    pip install selenium
"""

import os
import time
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# ----------------------------------------------------------------------
# CONFIGURACIÓN — datos extraídos de la cotización S15603 (PDF)
# ----------------------------------------------------------------------
RUTA_ARCHIVO = "file:///C:/Users/gvelazquez/Downloads/logi-stock-erp.html"

FACTURA = {
    "nro_fiscal": "A-15603",
    "proveedor_texto": "LabQuímica Austral",
    "fecha_emision": "2026-08-12",
    "condicion": "Crédito",     # <- antes "Contado"
    "plazo_dias": "30",
    "cantidad": "1",
    "precio_unit": "345",
    "lote": "L-15603",
    "lote_vencimiento": "2027-08-12",
}

VELOCIDAD_TIPEO = 0.09
PAUSA_ENTRE_PASOS = 0.7


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
def esperar(segundos=PAUSA_ENTRE_PASOS):
    time.sleep(segundos)


def resaltar(driver, element, color="#ff3b3b"):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'}); "
        "arguments[0].style.outline = '3px solid ' + arguments[1]; "
        "arguments[0].style.outlineOffset = '2px';",
        element, color,
    )
    time.sleep(0.9)  # tiempo que queda visible el resalte antes de actuar — subilo/bajalo a gusto


def quitar_resalte_seguro(driver, element):
    """Igual que quitar el resalte, pero no falla si el elemento ya no existe
    en el DOM (pasa cuando la tabla se re-renderiza justo después)."""
    try:
        driver.execute_script("arguments[0].style.outline = '';", element)
    except Exception:
        pass


def disparar_change(driver, element):
    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", element
    )


def tipear_lento(driver, element, texto, disparar_change_final=True):
    """Escribe letra por letra. Usa Ctrl+A para seleccionar el contenido
    existente en vez de element.clear(): .clear() dispara el evento
    'change' por su cuenta (así lo define el protocolo WebDriver), y en
    esta app eso re-renderiza toda la fila de la tabla ANTES de que
    lleguemos a tipear nada — dejando el elemento referenciado stale
    (StaleElementReferenceException) en el primer carácter. Ctrl+A solo
    selecciona texto, no dispara 'change', así que evita el problema."""
    resaltar(driver, element)
    element.click()
    element.send_keys(Keys.CONTROL, "a")
    for letra in texto:
        element.send_keys(letra)
        time.sleep(VELOCIDAD_TIPEO)
    if disparar_change_final:
        disparar_change(driver, element)
    quitar_resalte_seguro(driver, element)
    esperar(0.3)


def elegir_select(driver, element, texto_visible):
    """Selecciona una opción por texto, ignorando acentos y mayúsculas.
    No usa Select().select_by_visible_text() porque exige coincidencia
    EXACTA de caracteres (incluido el acento tal cual está codificado),
    y una diferencia mínima ahí hace que falle sin avisar y corte todo
    el script en ese punto."""
    resaltar(driver, element)
    encontrado = driver.execute_script(
        """
        const el = arguments[0];
        const normalizar = s => s.normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().trim();
        const buscado = normalizar(arguments[1]);
        for (const opt of el.options) {
            if (normalizar(opt.textContent).includes(buscado)) {
                el.value = opt.value;
                el.dispatchEvent(new Event('change', {bubbles:true}));
                return true;
            }
        }
        return false;
        """,
        element, texto_visible,
    )
    quitar_resalte_seguro(driver, element)
    esperar(0.3)
    if not encontrado:
        raise ValueError(f'No encontré la opción "{texto_visible}" en el combo {element.get_attribute("id")}')


def click_visible(driver, element):
    resaltar(driver, element)
    element.click()
    quitar_resalte_seguro(driver, element)
    esperar()


def input_de_fila(driver, indice):
    """Vuelve a buscar el input N de la primera fila de la tabla de líneas.
    Se llama SIEMPRE justo antes de usarlo, porque la fila se puede haber
    reconstruido desde la última vez."""
    fila = driver.find_element(By.CSS_SELECTOR, ".lineas-table tbody tr")
    inputs = fila.find_elements(By.TAG_NAME, "input")
    print(f"   → la fila tiene {len(inputs)} <input> (se esperan 4: cantidad, precio, lote, vto.lote)")
    return inputs[indice]


def completar_campo_fila(driver, indice, texto, nombre, es_fecha=False):
    """Resalta, completa (tipeado o seteo directo si es fecha) y confirma
    el cambio, siempre re-consultando el elemento fresco."""
    print(f"Completando '{nombre}' con valor '{texto}'...")
    campo = input_de_fila(driver, indice)
    if es_fecha:
        resaltar(driver, campo)
        driver.execute_script("arguments[0].value = arguments[1];", campo, texto)
        disparar_change(driver, campo)
        quitar_resalte_seguro(driver, campo)
        esperar(0.3)
    else:
        tipear_lento(driver, campo, texto)
    print(f"   ✓ '{nombre}' completado")


# ----------------------------------------------------------------------
# FLUJO PRINCIPAL
# ----------------------------------------------------------------------
def main():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=options)
    driver.maximize_window()
    wait = WebDriverWait(driver, 10)

    # 1) Abrir app y loguear
    print("Abriendo la app...")
    driver.get(RUTA_ARCHIVO)
    esperar(1)
    boton_login = wait.until(EC.element_to_be_clickable((By.ID, "loginBtn")))
    click_visible(driver, boton_login)
    esperar(1)
    print("✓ Login hecho")

    # 2) Ir a "Comprobantes"
    print("Yendo a Comprobantes...")
    item_comprobantes = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, '.item[data-screen="comprobantes"]'))
    )
    click_visible(driver, item_comprobantes)
    esperar()
    print("✓ En Comprobantes")

    # 3) "Nuevo comprobante"
    print("Abriendo modal 'Nuevo comprobante'...")
    boton_nuevo = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Nuevo comprobante')]"))
    )
    click_visible(driver, boton_nuevo)
    esperar()
    print("✓ Modal abierto")

    # 4) Cabecera
    print("Completando N° fiscal...")
    campo_nro_fiscal = wait.until(EC.presence_of_element_located((By.ID, "fCompNroFiscal")))
    tipear_lento(driver, campo_nro_fiscal, FACTURA["nro_fiscal"])
    print("✓ N° fiscal completado")

    print("Eligiendo proveedor...")
    select_proveedor = driver.find_element(By.ID, "fCompProveedor")
    elegir_select(driver, select_proveedor, FACTURA["proveedor_texto"])
    print("✓ Proveedor elegido")

    print("Completando fecha de emisión...")
    campo_emision = driver.find_element(By.ID, "fCompEmision")
    resaltar(driver, campo_emision)
    driver.execute_script("arguments[0].value = arguments[1];", campo_emision, FACTURA["fecha_emision"])
    disparar_change(driver, campo_emision)
    quitar_resalte_seguro(driver, campo_emision)
    esperar()
    print("✓ Fecha de emisión completada")

    print("Cambiando condición de pago...")
    select_condicion = driver.find_element(By.ID, "fCompCondicion")
    elegir_select(driver, select_condicion, FACTURA["condicion"])
    print("✓ Condición de pago cambiada")

    # Si es Crédito, el campo "Plazo (días)" se habilita — lo completamos también
    if FACTURA["condicion"] == "Crédito":
        print("Completando plazo (días)...")
        campo_plazo = driver.find_element(By.ID, "fCompPlazo")
        tipear_lento(driver, campo_plazo, FACTURA["plazo_dias"])
        print("✓ Plazo completado")

    # 5) Línea de artículo (el artículo RC-2824 ya viene seleccionado por defecto)
    #    Orden de los <input> dentro de la fila: [cantidad, precio, lote, vto.lote]
    print("Buscando la fila de la tabla de líneas...")
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".lineas-table tbody tr")))
        completar_campo_fila(driver, 0, FACTURA["cantidad"], "Cantidad")
        completar_campo_fila(driver, 1, FACTURA["precio_unit"], "Precio unitario")
        completar_campo_fila(driver, 2, FACTURA["lote"], "Lote")
        completar_campo_fila(driver, 3, FACTURA["lote_vencimiento"], "Vto. lote", es_fecha=True)
    except Exception:
        ruta_captura = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error_screenshot.png")
        driver.save_screenshot(ruta_captura)
        print(f"❌ Falló completando la línea. Capturé pantalla en: {ruta_captura}")
        raise

    # 6) Guardar
    print("Guardando comprobante...")
    boton_guardar = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Guardar comprobante')]"))
    )
    click_visible(driver, boton_guardar)
    esperar(1.5)

    print("✅ Factura cargada — campo a campo, resaltando cada paso, sin tocar el mouse.")
    return driver


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n" + "=" * 60)
        print("❌ EL SCRIPT SE DETUVO ACÁ:")
        traceback.print_exc()
        print("=" * 60)
    finally:
        input("\nPresioná ENTER para cerrar esta ventana...")
