# ==============================================================================
# MOTOR NAIC v0.8.0 - INTÉRPRETE DE INTENCIONES IA Y PROCESAMIENTO VISUAL
# Repositorio Oficial: https://github.com
# ==============================================================================
import sys
import locale
import cv2
import pyttsx3
import speech_recognition as sr
import ollama
import json
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
        self.idiomas_soportados = {}  
        self.mapeo_nombres = {        
            'español': 'spanish', 'spanish': 'es', 'inglés': 'en', 'english': 'en',
            'francés': 'fr', 'french': 'fr', 'alemán': 'de', 'german': 'de', 'deutsch': 'de', 'italiano': 'it'
        }
        
        self.escanear_voces_del_sistema()
        self.idioma_activa = self.detectar_idioma_natal()

        # UI, Control y Visión
        self.root = None
        self.lbl_video = None
        self.txt_consola = None
        self.btn_micro = None
        self.contador_frames = 0
        self.rostros_detectados_cache = []
        self.ultimo_frame_bgr = None  # Almacena de forma segura el último frame capturado

    def escanear_voces_del_sistema(self):
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
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.kernel32.GetUserDefaultLocaleName.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
            ctypes.windll.kernel32.GetUserDefaultLocaleName.restype = ctypes.c_int
            buf = ctypes.create_unicode_buffer(85)
            resultado = ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)
            if resultado > 0:
                return buf.value.lower().strip()
            
        try:
            locale.setlocale(locale.LC_ALL, '')
            idioma_posix, _ = locale.getlocale()
            if idioma_posix:
                solo_idioma = idioma_posix.split('.')[0]
                return solo_idioma.replace('_', '-').lower()
        except Exception:
            pass
        return 'en-us'

    def detectar_idioma_natal(self):
        try:
            prefijo = self.obtener_prefijo_idioma() 
            print(f"Idioma del sistema detectado: {prefijo}")
            for code in self.idiomas_soportados:
                if prefijo.startswith(code) or code.startswith(prefijo.split('-')[0]):
                    return code
            return 'en-us'
        except Exception:
            return 'en-us'

    def hablar(self, texto, codigo_idioma=None):
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

    # ==============================================================================
    # PROPUESTA 1: INTERPRETE DE INTENCIONES CON FILOSOFÍA "ZERO-PARSER"
    # ==============================================================================
    def UI_ejecutar_archivo_naic(self):
        """ Inicia la lectura del script local en un hilo secundario """
        ruta = "programa.naic"
        self.actualizar_consola(f"[Intérprete]: Intentando abrir '{ruta}'...")
        
        def hilo_interprete():
            try:
                with open(ruta, 'r', encoding='utf-8') as archivo:
                    lineas = archivo.readlines()
                
                for idx, linea in enumerate(lineas, 1):
                    linea_limpia = linea.strip()
                    if not linea_limpia or linea_limpia.startswith('#'):
                        continue
                        
                    self.actualizar_consola(f"[Script L{idx}]: Procesando Intención -> '{linea_limpia}'")
                    self.ejecutar_linea_con_ia(linea_limpia)
            except FileNotFoundError:
                self.actualizar_consola(f"[Error]: Crea un archivo 'programa.naic' en el directorio raíz.")
            except Exception as e:
                self.actualizar_consola(f"[Error de Script]: {e}")

        threading.Thread(target=hilo_interprete, daemon=True).start()

    def ejecutar_linea_con_ia(self, linea_script):
        """ Usa Ollama para extraer comandos JSON estructurados omitiendo errores de sintaxis """
        prompt_sistema = (
            "Eres el núcleo del intérprete semántico NAIC. Convierte la instrucción en un objeto JSON plano.\n"
            "Funciones válidas:\n"
            "1. {\"funcion\": \"traducir\", \"idioma_destino\": \"nombre_idioma\"}\n"
            "2. {\"funcion\": \"vision\", \"idioma_destino\": \"nombre_idioma\"}\n"
            "Regla estricta: Devuelve solo JSON, sin formatos markdown ni textos adicionales."
        )

        try:
            respuesta = self.cliente_ollama.generate(
                model=self.modelo_local, 
                system=prompt_sistema,
                prompt=f"Instrucción a mapear: {linea_script}"
            )
            
            datos = json.loads(respuesta['response'].strip())
            funcion = datos.get("funcion")
            idioma = datos.get("idioma_destino", "ingles").lower().strip()

            if funcion == "traducir":
                self._procesar_voz_fondo_script(idioma)
            elif funcion == "vision":
                self._procesar_vision_fondo(idioma)
                
        except Exception as e:
            self.actualizar_consola(f"[Error de Interpretación IA]: {e}")

    def _procesar_voz_fondo_script(self, idioma_solicitado):
        """ Ejecución automatizada de traducción desde guion """
        with sr.Microphone() as fuente:
            try:
                self.reconocedor.adjust_for_ambient_noise(fuente, duration=0.6)
                self.actualizar_consola(f"[🎙️]: Escuchando frase para traducir al '{idioma_solicitado}'...")
                audio = self.reconocedor.listen(fuente, timeout=7, phrase_time_limit=8)
                
                frase_usuario = self.reconocedor.recognize_google(audio, language=self.idioma_activa)
                self.actualizar_consola(f"[Estudiante]: {frase_usuario}")

                self.ejecutar_traduccion_llm(frase_usuario, idioma_solicitado)
            except Exception as e:
                self.actualizar_consola(f"[Script Error]: {e}")

    # ==============================================================================
    # PROPUESTA 2: CAPACIDADES VISUALES AVANZADAS (OPENCV + LLM)
    # ==============================================================================
    def _procesar_vision_fondo(self, idioma_solicitado):
        """ Captura el entorno, analiza los rostros y genera un reporte hablado """
        if self.ultimo_frame_bgr is None:
            self.actualizar_consola("[Visión]: Cámara apagada o frame inválido.")
            return

        self.actualizar_consola("[Visión]: Capturando escena actual...")
        num_rostros = len(self.rostros_detectados_cache)

        # Prompt para que Ollama interprete los datos numéricos de la cámara
        prompt = (
            f"El subsistema OpenCV detectó {num_rostros} rostros humanos frente a la pantalla. "
            f"Genera un reporte descriptivo breve y amigable sobre lo que el sistema ve. "
            f"El reporte debe ser escrito en idioma {idioma_solicitado} y tener un máximo de dos frases."
        )

        self.actualizar_consola(f"[Naic]: Generando análisis visual en {idioma_solicitado}...")
        
        # Animación no bloqueante
        pensando = True
        def animar():
            if pensando and self.txt_consola:
                self.txt_consola.insert(tk.END, "👁️")
                self.txt_consola.see(tk.END)
                self.root.after(400, animar)
        self.root.after(400, animar)

        try:
            respuesta = self.cliente_ollama.generate(model=self.modelo_local, prompt=prompt)
            pensando = False
            self.actualizar_consola("\n")

            reporte = respuesta['response'].strip().replace('"', '')
            
            # Buscamos correspondencia de voz
            codigo_dest = self.mapeo_nombres.get(idioma_solicitado, idioma_solicitado[:2])
            for code in self.idiomas_soportados.keys():
                if codigo_dest in code:
                    codigo_dest = code
                    break

            self.hablar(reporte, codigo_idioma=codigo_dest)
        except Exception as e:
            pensando = False
            self.actualizar_consola(f"[Error de Visión]: {e}")

    def ejecutar_traduccion_llm(self, frase, idioma_destino):
        """ Envía la petición a Ollama limpiando caracteres raros """
        prompt = f"Traduce al {idioma_destino}, devuelve únicamente el texto traducido: '{frase}'"
        
        pensando = True
        def animar():
            if pensando and self.txt_consola:
                self.txt_consola.insert(tk.END, ".")
                self.txt_consola.see(tk.END)
                self.root.after(400, animar)
        self.root.after(400, animar)

        try:
            respuesta = self.cliente_ollama.generate(model=self.modelo_local, prompt=prompt)
            pensando = False
            self.actualizar_consola("\n")
            
            traduccion = respuesta['response'].strip().replace('"', '')
            
            codigo_dest = self.mapeo_nombres.get(idioma_destino, idioma_destino[:2])
            for code in self.idiomas_soportados.keys():
                if codigo_dest in code:
                    codigo_dest = code
                    break

            self.hablar(traduccion, codigo_idioma=codigo_dest)
        except Exception as e:
            pensando = False
            self.actualizar_consola(f"[Error LLM]: {e}")

    def UI_activar_microfono(self):
        """ Botón manual clásico para interactuar oralmente (Doble Escucha) """
        self.btn_micro.config(state=tk.DISABLED, text="⏳ ESCUCHANDO...")
        
        def flujo_manual():
            with sr.Microphone() as fuente:
                try:
                    self.reconocedor.adjust_for_ambient_noise(fuente, duration=0.6)
                    self.actualizar_consola("[🎙️]: ESCUCHANDO FRASE... Habla ahora.")
                    audio_frase = self.reconocedor.listen(fuente, timeout=7, phrase_time_limit=8)
                    
                    frase_usuario = self.reconocedor.recognize_google(audio_frase, language=self.idioma_activa)
                    self.actualizar_consola(f"[Estudiante]: {frase_usuario}")

                    self.hablar("¿A qué idioma quieres traducir esta frase?")
                    
                    self.actualizar_consola("[🎙️]: ESCUCHANDO IDIOMA...")
                    time.sleep(0.2)
                    audio_idioma = self.reconocedor.listen(fuente, timeout=5, phrase_time_limit=4)
                    
                    idioma_escuchado = self.reconocedor.recognize_google(audio_idioma, language=self.idioma_activa)
                    idioma_solicitado = idioma_escuchado.lower().strip()
                    self.actualizar_consola(f"[Idioma Solicitado]: {idioma_solicitado}")

                    self.ejecutar_traduccion_llm(frase_usuario, idioma_solicitado)
                except Exception as e:
                    self.actualizar_consola(f"[Oído/Sistema]: Error o silencio. {e}")
            
            self.root.after(0, lambda: self.btn_micro.config(state=tk.NORMAL, text="🎤 ACTIVAR MICRÓFONO"))

        threading.Thread(target=flujo_manual, daemon=True).start()

    def UI_actualizar_camara(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.ultimo_frame_bgr = frame.copy() # Almacén seguro para el procesador de visión
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
        self.root.title("NaturAICode Studio v0.8.0")
        self.root.geometry("950x550")
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
        self.btn_micro.pack(fill=tk.X, padx=10, pady=5)

        # BOTÓN INTEGRADO DEL INTÉRPRETE DE ARCHIVOS
        self.btn_script = tk.Button(frame_der, text="📄 EJECUTAR SCRIPT .NAIC", bg="#2196F3", fg="white", command=self.UI_ejecutar_archivo_naic)
        self.btn_script.pack(fill=tk.X, padx=10, pady=5)

        self.UI_actualizar_camara()
        self.actualizar_consola(f"[Sistema]: Motor listo. Natal: {self.idioma_activa}")
        self.root.mainloop()

if __name__ == "__main__":
    naic = Naic()
    naic.iniciar_interfaz_grafica()
