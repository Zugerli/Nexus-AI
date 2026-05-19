# ==============================================================================
# LIBRERÍAS REQUERIDAS:
# pip install opencv-python pyttsx3 ollama openai SpeechRecognition pyaudio pillow
# ==============================================================================

# ==============================================================================
# MOTOR NAIC v0.7.4 - ACTUALIZADO COMPATIBILIDAD 2026
# ==============================================================================
import sys
import locale
import cv2
import pyttsx3
import speech_recognition as sr
import ollama
import threading
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

class Naic:
    def __init__(self):
        self.cap = None
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.reconocedor = sr.Recognizer()

        self.modelo_local = "llama3:8b"
        self.cliente_ollama = ollama.Client()

        # --- LÓGICA DINÁMICA DE VOCES ---
        self.idiomas_soportados = {}  # Se llenará dinámicamente: {'es-ES': <Voice Object>, ...}
        self.mapeo_nombres = {        # Para traducir nombres comunes a códigos de lenguaje
            'español': 'spanish', 'spanish': 'es', 'inglés': 'en', 'english': 'en',
            'francés': 'fr', 'french': 'fr', 'alemán': 'de', 'german': 'de', 'deutsch': 'de', 'italiano': 'it'
        }
        
        self.escanear_voces_del_sistema()
        self.idioma_activa = self.detectar_idioma_natal()

        # UI y Control
        self.root = None
        self.lbl_video = None
        self.txt_consola = None
        self.btn_micro = None
        self.contador_frames = 0
        self.rostros_detectados_cache = []

    def ejecutar_archivo_naic(self, ruta_archivo):
        """ Lee un archivo .naic línea por línea y procesa sus comandos """
        self.actualizar_consola(f"[Intérprete]: Leyendo archivo '{ruta_archivo}'...")
        try:
            with open(ruta_archivo, 'r', encoding='utf-8') as archivo:
                lineas = archivo.readlines()
                
            for i, linea in enumerate(lineas, 1):
                linea_limpia = linea.strip()
                # Ignorar líneas vacías o comentarios que empiecen con #
                if not linea_limpia or linea_limpia.startswith('#'):
                    continue
                    
                self.actualizar_consola(f"[Línea {i}]: Ejecutando -> {linea_limpia}")
                self.interpretar_linea(linea_limpia)
        except FileNotFoundError:
            self.actualizar_consola(f"[Error]: El archivo '{ruta_archivo}' no existe.")
        except Exception as e:
            self.actualizar_consola(f"[Error en intérprete]: {e}")

    def interpretar_linea(self, linea):
        """ Analiza la sintaxis de una línea y ejecuta la acción correspondiente """
        # Comando: escuchar.traducir(a: "idioma")
        if "escuchar.traducir(" in linea:
            try:
                # Extraemos el contenido dentro de las comillas de forma segura
                # Ejemplo: de 'escuchar.traducir(a: "ingles")' extrae 'ingles'
                partes = linea.split('("') if '("' in linea else linea.split('("')
                if len(partes) < 2:
                    # Intento alternativo por si usaron comillas simples o espacios
                    partes = linea.split('"')
                
                idioma_destino = partes[1].split('"')[0].strip().lower()
                
                # Ejecutamos la lógica en un hilo para no congelar la UI de Tkinter
                self.btn_micro.config(state=tk.DISABLED, text="⏳ NAIC SCRIPT...")
                
                # Reutilizamos tu lógica de fondo pasándole directamente el idioma prefijado
                hilo_script = threading.Thread(
                    target=self._procesar_voz_fondo_script, 
                    args=(idioma_destino,), 
                    daemon=True
                )
                hilo_script.start()
                
            except Exception as e:
                self.actualizar_consola(f"[Error de Sintaxis]: No se pudo parsear el comando. {e}")

    def escanear_voces_del_sistema(self):
        """ Escanea voces reales y las mapea en self.idiomas_soportados """
        engine = pyttsx3.init()
        voces = engine.getProperty('voices')
        
        print("\n--- [SISTEMA DE VOCES DETECTADO] ---")
        for voice in voces:
            for lang in voice.languages:
                lang_code = lang.replace('_', '-').lower()
                self.idiomas_soportados[lang_code] = voice
                print(f" > Detectado: {lang_code} (Voz: {voice.name})")
        print("------------------------------------\n")

    def obtener_prefijo_idioma(self):
        """ Obtiene el identificador ISO de configuración regional sin usar APIs obsoletas """
        # --- DETECCIÓN PARA WINDOWS (Nativo y Forzado BCP-47) ---
        if sys.platform == 'win32':
            import ctypes
        
            # Declaramos GetUserDefaultLocaleName (Evuelve siempre el tag corto: es-AR, en-US, etc.)
            ctypes.windll.kernel32.GetUserDefaultLocaleName.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
            ctypes.windll.kernel32.GetUserDefaultLocaleName.restype = ctypes.c_int
        
            buf = ctypes.create_unicode_buffer(85)
            resultado = ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)
            
            if resultado > 0:
                return buf.value.lower().strip()
            
        # --- DETECCIÓN PARA LINUX / MACOS ---
        try:
            locale.setlocale(locale.LC_ALL, '')
            idioma_posix, _ = locale.getlocale()
            
            if idioma_posix:
                solo_idioma = idioma_posix.split('.')[0]
                return solo_idioma.replace('_', '-').lower()
        except Exception:
            pass
        return 'en-us'  # Fallback definitivo en caso de error

    def detectar_idioma_natal(self):
        """ Detecta el idioma del SO y verifica si tenemos voz para él """
        try:
            prefijo = self.obtener_prefijo_idioma() 
            print(f"Idioma del sistema detectado: {prefijo}")
            
            # Intentamos coincidencia exacta (es-ar) o parcial (es)
            for code in self.idiomas_soportados:
                if prefijo.startswith(code) or code.startswith(prefijo.split('-')[0]):
                    return code
            return 'en-us' # Fallback reactivado por seguridad
        except Exception:
            return 'en-us'

    def hablar(self, texto, codigo_idioma=None):
        """ Habla en el idioma solicitado si la voz existe o usa fallback """
        if not codigo_idioma:
            codigo_idioma = self.idioma_activa

        self.actualizar_consola(f"[Naic]: {texto}")

        engine = pyttsx3.init()
        voz_encontrada = None
        
        for code, voice_obj in self.idiomas_soportados.items():
            if codigo_idioma.lower() in code:
                voz_encontrada = voice_obj.id
                break
        
        if voz_encontrada:
            engine.setProperty('voice', voz_encontrada)
        else:
            self.actualizar_consola(f"[⚠️] Voz para '{codigo_idioma}' no instalada. Usando natal.")
            if self.idioma_activa in self.idiomas_soportados:
                engine.setProperty('voice', self.idiomas_soportados[self.idioma_activa].id)

        engine.say(texto)
        engine.runAndWait()
        engine.stop()

    def actualizar_consola(self, texto):
        print(texto)
        if self.txt_consola:
            self.txt_consola.insert(tk.END, texto + "\n")
            self.txt_consola.see(tk.END)
            self.root.update_idletasks()

    def UI_activar_microfono(self):
        """ Deshabilita el botón e inicia el hilo de procesamiento de voz """
        self.btn_micro.config(state=tk.DISABLED, text="⏳ ESCUCHANDO...")
        
        # Lanzamos el proceso en un hilo separado (daemon=True para que cierre si cierras la ventana)
        hilo_voz = threading.Thread(target=self._procesar_voz_fondo, daemon=True)
        hilo_voz.start()

    def _procesar_voz_fondo_script(self, idioma_solicitado_limpio):
        """ Variante automatizada para el intérprete de scripts .naic """
        with sr.Microphone() as fuente:
            try:
                # 1. Captura de la frase
                self.actualizar_consola("[Sistema Script]: Ajustando ruido ambiental...")
                self.reconocedor.adjust_for_ambient_noise(fuente, duration=0.6)
                
                self.actualizar_consola(f"[🎙️ Script]: Escuchando frase para traducir al '{idioma_solicitado_limpio}'...")
                audio_frase = self.reconocedor.listen(fuente, timeout=7, phrase_time_limit=8)
                
                frase_usuario = self.reconocedor.recognize_google(audio_frase, language=self.idioma_activa)
                self.actualizar_consola(f"[Estudiante]: {frase_usuario}")

                # 2. Validación de paquete de voz
                codigo_dest = None
                idioma_encontrado_mapeo = None
                
                for nombre_comun, sigla in self.mapeo_nombres.items():
                    if nombre_comun in idioma_solicitado_limpio:
                        codigo_dest = sigla
                        idioma_encontrado_mapeo = nombre_comun
                        break

                if not codigo_dest:
                    codigo_dest = idioma_solicitado_limpio[:2]
                    idioma_encontrado_mapeo = idioma_solicitado_limpio

                voz_disponible = False
                for code in self.idiomas_soportados.keys():
                    if codigo_dest in code:
                        voz_disponible = True
                        codigo_dest = code
                        break

                # 3. Traducción o rechazo educativo
                if voz_disponible:
                    prompt = f"Traduce al {idioma_encontrado_mapeo}, devuelve única y exclusivamente el texto traducido: '{frase_usuario}'"
                    self.actualizar_consola(f"[Naic]: Traduciendo...")
                    
                    respuesta = self.cliente_ollama.generate(model=self.modelo_local, prompt=prompt)
                    traduccion = respuesta['response'].strip().replace('"', '')
                    
                    self.hablar(traduccion, codigo_idioma=codigo_dest)
                else:
                    mensaje_error = f"No puedo traducir a ese idioma porque la voz de {idioma_encontrado_mapeo} no está instalada en Windows."
                    self.actualizar_consola(f"[⚠️ Error]: Voz para '{idioma_encontrado_mapeo}' no encontrada.")
                    self.hablar(mensaje_error)

            except Exception as e:
                self.actualizar_consola(f"[Error Script]: {e}")

        self.root.after(0, lambda: self.btn_micro.config(state=tk.NORMAL, text="🎤 ACTIVAR MICRÓFONO"))

    def UI_actualizar_camara(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.contador_frames += 1
                if self.contador_frames % 4 == 0:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    self.rostros_detectados_cache = self.face_cascade.detectMultiScale(gray, 1.2, 4)
                for (x, y, w, h) in self.rostros_detectados_cache:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(cv2image)
                imgtk = ImageTk.PhotoImage(image=img)
                self.lbl_video.imgtk = imgtk
                self.lbl_video.configure(image=imgtk)
            self.lbl_video.after(15, self.UI_actualizar_camara)

    def iniciar_interfaz_grafica(self):
        self.root = tk.Tk()
        self.root.title("Naic-AI Studio v0.7.3 - Dynamic Voice Engine")
        self.root.geometry("900x550")
        self.root.configure(bg="#1e1e1e")

        frame_izq = tk.Frame(self.root, bg="#1e1e1e")
        frame_izq.pack(side=tk.LEFT, padx=15, pady=15, fill=tk.BOTH, expand=True)

        self.lbl_video = tk.Label(frame_izq, bg="#000000")
        self.lbl_video.pack(fill=tk.BOTH, expand=True)

        self.cap = cv2.VideoCapture(0)
        
        frame_der = tk.Frame(self.root, bg="#2d2d2d", width=350)
        frame_der.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(0, 15), pady=15)

        self.txt_consola = tk.Text(frame_der, bg="#121212", fg="#00ff00", font=("Consolas", 9))
        self.txt_consola.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.btn_micro = tk.Button(frame_der, text="🎤 ACTIVAR MICRÓFONO", bg="#4CAF50", fg="white", command=self.UI_activar_microfono)
        self.btn_micro.pack(fill=tk.X, padx=10, pady=15)

        # Botón para ejecutar un script de prueba
        self.btn_script = tk.Button(
            frame_der, 
            text="📄 EJECUTAR SCRIPT .NAIC", 
            bg="#2196F3", 
            fg="white", 
            command=lambda: self.ejecutar_archivo_naic("programa.naic")
        )
        self.btn_script.pack(fill=tk.X, padx=10, pady=5)


        self.UI_actualizar_camara()
        self.actualizar_consola(f"[Sistema]: Voces listas. Idioma natal: {self.idioma_activa}")
        self.root.mainloop()

if __name__ == "__main__":
    naic = Naic()
    naic.iniciar_interfaz_grafica()
