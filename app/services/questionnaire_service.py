import json
import logging
import os
import random
from typing import Dict, Any, Optional, List, Tuple, Union

from app.models.conversation import Conversation, QuestionnaireState
from app.config import settings

logger = logging.getLogger("hydrous-backend")


class QuestionnaireService:
    """Servicio mejorado para manejar el cuestionario y sus respuestas de forma conversacional"""

    def __init__(self):
        self.questionnaire_data = self._load_questionnaire_data()
        # Frases de transición para hacer más fluido el cuestionario
        self.transitions = [
            "Entendido. Ahora",
            "Perfecto. A continuación,",
            "Gracias por esa información.",
            "Excelente. Sigamos con",
            "Muy bien.",
            "Comprendo.",
            "Esa información es útil.",
            "Avancemos con",
            "Continuemos.",
            "Ahora necesitaría saber",
        ]
        # Frases para solicitar clarificación
        self.clarification_phrases = [
            "No estoy seguro de haber entendido tu respuesta. ¿Podrías por favor",
            "Disculpa, pero necesito una respuesta más clara. ¿Podrías",
            "Para asegurarme de registrar correctamente tu respuesta, ¿podrías",
            "Necesito un poco más de claridad en tu respuesta. ¿Te importaría",
        ]
        # Frases para confirmación
        self.confirmation_phrases = [
            "He registrado que",
            "Entiendo que",
            "He anotado que",
            "Perfecto, he guardado que",
        ]

    def _load_questionnaire_data(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario desde un archivo JSON"""
        try:
            questionnaire_path = os.path.join(
                os.path.dirname(__file__), "../data/questionnaire.json"
            )
            if os.path.exists(questionnaire_path):
                with open(questionnaire_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.warning(
                    "Archivo de cuestionario no encontrado. Usando estructura predeterminada."
                )
                return self._build_default_questionnaire()
        except Exception as e:
            logger.error(f"Error al cargar datos del cuestionario: {str(e)}")
            return self._build_default_questionnaire()

    def _build_default_questionnaire(self) -> Dict[str, Any]:
        """Construye una versión predeterminada del cuestionario para emergencias"""
        # Estructura mínima para que el sistema funcione en caso de error
        return {
            "sectors": ["Industrial", "Comercial", "Municipal", "Residencial"],
            "subsectors": {"Industrial": ["Textil"]},
            "questions": {
                "Industrial_Textil": [
                    {
                        "id": "nombre_empresa",
                        "text": "¿Cuál es el nombre de tu empresa o cómo prefieres que te llame?",
                        "type": "text",
                        "required": True,
                    }
                ]
            },
        }

    def get_sectors(self) -> List[str]:
        """Obtiene la lista de sectores disponibles"""
        return self.questionnaire_data.get("sectors", [])

    def get_subsectors(self, sector: str) -> List[str]:
        """Obtiene los subsectores para un sector dado"""
        subsectors = self.questionnaire_data.get("subsectors", {})
        return subsectors.get(sector, [])

    def get_random_fact(self, sector: str, subsector: str) -> Optional[str]:
        """Obtiene un hecho aleatorio relacionado con el sector/subsector"""
        facts_key = f"{sector}_{subsector}"
        facts = self.questionnaire_data.get("facts", {}).get(facts_key, [])
        return random.choice(facts) if facts else None

    def get_introduction(self) -> Tuple[str, str]:
        """Obtiene el texto de introducción del cuestionario"""
        intro = self.questionnaire_data.get("introduction", {})
        text = intro.get("text", "")
        explanation = intro.get("explanation", "")

        # Asegurar que la introducción es conversacional
        if not text:
            text = "¡Hola! Soy el Diseñador de Soluciones de Agua con IA de Hydrous, tu asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales."

        if not explanation:
            explanation = "Para desarrollar la mejor solución para tus instalaciones, te haré algunas preguntas específicas para recopilar los datos necesarios y crear una propuesta personalizada."

        return text, explanation

    def get_next_question(self, state: QuestionnaireState) -> Optional[Dict[str, Any]]:
        """Obtiene la siguiente pregunta basada en el estado actual"""
        if not state.active:
            return None

        if not state.sector:
            return {
                "id": "sector_selection",
                "text": "¿En qué sector opera tu empresa?",
                "type": "multiple_choice",
                "options": self.get_sectors(),
                "required": True,
                "explanation": "El sector determina el tipo de aguas residuales y las tecnologías más adecuadas para su tratamiento.",
            }

        if not state.subsector:
            return {
                "id": "subsector_selection",
                "text": f"Dentro del sector {state.sector}, ¿cuál es el giro específico de tu empresa?",
                "type": "multiple_choice",
                "options": self.get_subsectors(state.sector),
                "required": True,
                "explanation": "Cada subsector tiene características específicas que influyen en el diseño de la solución óptima para tus necesidades.",
            }

        # Obtener las preguntas para este sector/subsector
        question_key = f"{state.sector}_{state.subsector}"
        questions = self.questionnaire_data.get("questions", {}).get(question_key, [])

        if not questions:
            # No hay preguntas para esta combinación de sector/subsector
            logger.warning(f"No se encontraron preguntas para {question_key}")
            return None

        # Determinar la siguiente pregunta no contestada
        for q in questions:
            if q["id"] not in state.answers:
                # Enriquecer la pregunta con un hecho relevante
                fact = self.get_random_fact(state.sector, state.subsector)

                # Hacer una copia para no modificar el original
                enriched_question = q.copy()

                # Mejorar el texto de la pregunta para hacerlo más conversacional
                enriched_question["text"] = self._make_question_conversational(
                    q["text"], q["id"]
                )

                # Añadir un hecho relevante a la explicación si existe
                if fact and enriched_question.get("explanation"):
                    enriched_question["explanation"] = (
                        f"{enriched_question['explanation']}\n\n*Dato interesante: {fact}*"
                    )
                elif fact:
                    enriched_question["explanation"] = f"*Dato interesante: {fact}*"

                return enriched_question

        # Si llegamos aquí, es que todas las preguntas han sido respondidas
        return None

    def _make_question_conversational(
        self, question_text: str, question_id: str
    ) -> str:
        """Hace que la pregunta suene más conversacional según su tipo"""

        # Si la pregunta ya tiene forma de pregunta, la dejamos como está
        if question_text.strip().endswith("?"):
            return question_text

        # Patrones comunes para convertir a formato de pregunta
        if "nombre" in question_id.lower():
            return f"¿Cuál es {question_text}?"
        elif "ubicacion" in question_id.lower():
            return f"¿Cuál es tu {question_text}?"
        elif "costo" in question_id.lower() or "precio" in question_id.lower():
            return f"¿Podrías indicarme {question_text}?"
        elif "cantidad" in question_id.lower() or "volumen" in question_id.lower():
            return f"¿Cuál es la {question_text}?"
        elif "objetivo" in question_id.lower():
            return f"¿Cuál es {question_text}?"

        # Si no hay un patrón específico, simplemente añadimos "¿Cuál es...?"
        return f"¿Podrías proporcionarnos información sobre {question_text}?"

    def process_answer(
        self, conversation: Conversation, question_id: str, answer: Any
    ) -> Union[bool, str]:
        """
        Procesa una respuesta y actualiza el estado del cuestionario de manera inteligente
        """
        # Guardar la respuesta
        conversation.questionnaire_state.answers[question_id] = answer

        # Procesar respuestas a las preguntas especiales (sector y subsector)
        if question_id == "sector_selection":
            # Intentar determinar el sector a partir de la respuesta
            sectors = self.get_sectors()

            if isinstance(answer, str):
                # Si es un numero, usarlo como indice
                if answer.isdigit():
                    sector_index = int(answer) - 1
                    if 0 <= sector_index < len(sectors):
                        conversation.questionnaire_state.sector = sectors[sector_index]
                # Si no es un numero, buscar coincidencia por texto
                else:
                    answer_lower = answer.lower()
                    for sector in sectors:
                        if (
                            sector.lower() in answer_lower
                            or answer_lower in sector.lower()
                        ):
                            conversation.questionnaire_state.sector = sector
                            break

            # Si no se pudo determinar el sector, usar el primero como falback
            if not conversation.questionnaire_state.sector and sectors:
                conversation.questionnaire_state.sector = sectors[0]

        elif question_id == "subsector_selection":
            if conversation.questionnaire_state.sector:
                subsectors = self.get_subsectors(
                    conversation.questionnaire_state.sector
                )

                if isinstance(answer, str):
                    # Si es un numero, usarlo como indice
                    if answer.isdigit():
                        subsector_index = int(answer) - 1
                        if 0 <= subsector_index < len(subsectors):
                            conversation.questionnaire_state.subsector = subsectors[
                                subsector_index
                            ]
                    # Si no es un numero, buscar coincidencia por texto
                    else:
                        answer_lower = answer.lower()
                        for subsector in subsectors:
                            if (
                                subsector.lower() in answer_lower
                                or answer_lower in subsector.lower()
                            ):
                                conversation.questionnaire_state.subsector = subsector
                                break

                # Si no se pudo determinar el subsector, usar el primero como falback
                if not conversation.questionnaire_state.subsector and subsectors:
                    conversation.questionnaire_state.subsector = subsectors[0]

        # Actualizar el ID de la pregunta actual
        next_question = self.get_next_question(conversation.questionnaire_state)
        conversation.questionnaire_state.current_question_id = (
            next_question["id"] if next_question else None
        )

        # Verificar si hemos completado el cuestionario
        if next_question is None:
            conversation.questionnaire_state.completed = True

        return True

    def _process_selection_answer(
        self, answer: Any, question: Dict[str, Any], state: QuestionnaireState
    ) -> Any:
        """
        Procesa una respuesta para preguntas de selección.
        Maneja tanto respuestas numéricas como texto.
        """
        options = question.get("options", [])
        if not options:
            return answer

        # Si es respuesta numérica
        if isinstance(answer, int) or (isinstance(answer, str) and answer.isdigit()):
            index = int(answer) - 1  # Ajustamos al índice base-0
            if 0 <= index < len(options):
                if question["type"] == "multiple_choice":
                    return options[index]  # Devolvemos el texto de la opción
                else:
                    return [options[index]]  # Para multiple_select devolvemos una lista
            return None

        # Si es una respuesta de texto para multiple_select (valores separados por coma)
        if (
            question["type"] == "multiple_select"
            and isinstance(answer, str)
            and "," in answer
        ):
            indices = []
            selected_options = []

            for part in answer.split(","):
                part = part.strip()
                if part.isdigit():
                    index = int(part) - 1
                    if 0 <= index < len(options):
                        selected_options.append(options[index])
                else:
                    # Buscar coincidencia por texto
                    matches = [opt for opt in options if part.lower() in opt.lower()]
                    selected_options.extend(matches)

            return selected_options if selected_options else None

        # Si es respuesta de texto, buscar coincidencia
        if isinstance(answer, str):
            # Primero buscar coincidencia exacta
            if answer in options:
                return answer

            # Luego buscar coincidencia parcial
            matches = [opt for opt in options if answer.lower() in opt.lower()]
            if len(matches) == 1:
                return matches[0]

        return None

    def _get_question_by_id(
        self, state: QuestionnaireState, question_id: str
    ) -> Optional[Dict[str, Any]]:
        """Obtiene los datos de una pregunta por su ID"""
        if question_id == "sector_selection":
            return {
                "id": "sector_selection",
                "text": "¿En qué sector opera tu empresa?",
                "type": "multiple_choice",
                "options": self.get_sectors(),
                "required": True,
            }

        if question_id == "subsector_selection" and state.sector:
            return {
                "id": "subsector_selection",
                "text": f"¿Cuál es el giro específico de tu empresa dentro del sector {state.sector}?",
                "type": "multiple_choice",
                "options": self.get_subsectors(state.sector),
                "required": True,
            }

        # Buscar en las preguntas específicas del sector/subsector
        if state.sector and state.subsector:
            question_key = f"{state.sector}_{state.subsector}"
            questions = self.questionnaire_data.get("questions", {}).get(
                question_key, []
            )

            for q in questions:
                if q["id"] == question_id:
                    return q

        return None

    def get_random_transition(self) -> str:
        """Devuelve una frase de transición aleatoria para hacer más fluido el cuestionario"""
        return random.choice(self.transitions)

    def get_clarification_phrase(self) -> str:
        """Devuelve una frase de solicitud de clarificación aleatoria"""
        return random.choice(self.clarification_phrases)

    def get_confirmation_phrase(self) -> str:
        """Devuelve una frase de confirmación aleatoria"""
        return random.choice(self.confirmation_phrases)

    def format_question_with_transition(
        self, question: Dict[str, Any], previous_answer: Optional[str] = None
    ) -> str:
        """
        Formatea una pregunta con una transición natural basada en la respuesta anterior.
        Hace que el cuestionario se sienta como una conversación.
        """
        transition = self.get_random_transition()

        # Si hay una respuesta anterior, confirmarla primero
        confirmation = ""
        if previous_answer:
            confirmation = f"{self.get_confirmation_phrase()} {previous_answer}. "

        result = f"{confirmation}{transition} {question['text']}"

        # Añadir explicación si existe
        if question.get("explanation"):
            result += f"\n\n*{question['explanation']}*"

        # Formatear opciones para preguntas de selección
        if question["type"] == "multiple_choice" and "options" in question:
            result += "\n\n"
            for i, option in enumerate(question["options"], 1):
                result += f"{i}. {option}\n"

        elif question["type"] == "multiple_select" and "options" in question:
            result += "\n\n"
            for i, option in enumerate(question["options"], 1):
                result += f"{i}. {option}\n"
            result += "\nPuedes seleccionar varias opciones separando los números con comas (ej: 1,3,4)."

        return result

    def is_questionnaire_complete(self, conversation: Conversation) -> bool:
        """Verifica si el cuestionario está completo"""
        return conversation.questionnaire_state.completed

    def generate_proposal(self, conversation: Conversation) -> Dict[str, Any]:
        """Genera una propuesta basada en las respuestas del cuestionario"""
        answers = conversation.questionnaire_state.answers
        sector = conversation.questionnaire_state.sector
        subsector = conversation.questionnaire_state.subsector

        # Extraer información básica
        client_name = answers.get("nombre_empresa", "Cliente")
        location = answers.get("ubicacion", "No especificada")

        # Determinar los objetivos del proyecto
        objectives = []
        if "objetivo_principal" in answers:
            obj_principal = answers["objetivo_principal"]
            if isinstance(obj_principal, int) or (
                isinstance(obj_principal, str) and obj_principal.isdigit()
            ):
                obj_index = int(obj_principal) - 1
                options = self._get_options_for_question(
                    "objetivo_principal", sector, subsector
                )
                if 0 <= obj_index < len(options):
                    objectives.append(options[obj_index])
            else:
                objectives.append(obj_principal)

        # Determinar objetivos de reúso
        reuse_objectives = []
        if "objetivo_reuso" in answers:
            reuse = answers["objetivo_reuso"]
            if isinstance(reuse, list):
                for r in reuse:
                    if isinstance(r, int) or (isinstance(r, str) and r.isdigit()):
                        r_index = int(r) - 1
                        options = self._get_options_for_question(
                            "objetivo_reuso", sector, subsector
                        )
                        if 0 <= r_index < len(options):
                            reuse_objectives.append(options[r_index])
                    else:
                        reuse_objectives.append(r)
            elif isinstance(reuse, int) or (isinstance(reuse, str) and reuse.isdigit()):
                r_index = int(reuse) - 1
                options = self._get_options_for_question(
                    "objetivo_reuso", sector, subsector
                )
                if 0 <= r_index < len(options):
                    reuse_objectives.append(options[r_index])
            else:
                reuse_objectives.append(reuse)

        # Extraer parámetros de agua residual
        wastewater_params = {}
        for param in ["sst", "dbo", "dqo", "ph", "color", "metales_pesados"]:
            if param in answers and answers[param]:
                wastewater_params[param] = answers[param]

        # Determinar flujo de agua
        flow_rate = answers.get("cantidad_agua_residual", "No especificado")

        # Generar recomendación de tratamiento básica
        treatment_recommendation = {
            "pretratamiento": {
                "descripcion": "Eliminación de sólidos gruesos y materiales flotantes",
                "tecnologias": ["Rejillas", "Tamices", "Desarenadores"],
                "eficiencia_esperada": "Eliminación del 90-95% de sólidos gruesos",
            },
            "primario": {
                "descripcion": "Remoción de sólidos suspendidos y parte de la materia orgánica",
                "tecnologias": [
                    "Flotación por aire disuelto (DAF)",
                    "Coagulación/Floculación",
                ],
                "eficiencia_esperada": "Reducción de 60-70% de SST, 30-40% de DQO",
            },
            "secundario": {
                "descripcion": "Degradación biológica de materia orgánica",
                "tecnologias": [
                    "Reactor biológico de membrana (MBR)",
                    "Reactor de biopelícula de lecho móvil (MBBR)",
                ],
                "eficiencia_esperada": "Reducción de 90-95% de DBO, 70-85% de DQO",
            },
            "terciario": {
                "descripcion": "Remoción de color y contaminantes residuales",
                "tecnologias": [
                    "Oxidación avanzada",
                    "Carbón activado",
                    "Nanofiltración",
                ],
                "eficiencia_esperada": "Reducción de 95-99% del color, 80-90% de contaminantes traza",
            },
        }

        # Estimar costos básicos
        cost_estimation = {
            "capex": {
                "equipos": 50000.0,
                "instalacion": 20000.0,
                "ingenieria": 10000.0,
                "total": 80000.0,
            },
            "opex": {
                "energia": 1000.0,
                "quimicos": 500.0,
                "mano_obra": 1500.0,
                "mantenimiento": 500.0,
                "total_mensual": 3500.0,
                "total_anual": 42000.0,
            },
        }

        # Calcular ROI básico
        roi = {
            "ahorro_anual": 60000.0,
            "periodo_recuperacion": 1.5,
            "roi_5_anos": 275.0,
        }

        # Construir propuesta completa
        proposal = {
            "client_info": {
                "name": client_name,
                "location": location,
                "sector": sector,
                "subsector": subsector,
            },
            "project_details": {
                "flow_rate": flow_rate,
                "objectives": objectives,
                "reuse_objectives": reuse_objectives,
            },
            "wastewater_parameters": wastewater_params,
            "recommended_treatment": treatment_recommendation,
            "cost_estimation": cost_estimation,
            "roi_analysis": roi,
            "disclaimer": self.questionnaire_data.get("proposal_template", {}).get(
                "disclaimer", ""
            ),
        }

        return proposal

    def _get_options_for_question(
        self, question_id: str, sector: str, subsector: str
    ) -> List[str]:
        """Obtiene las opciones para una pregunta específica"""
        question_key = f"{sector}_{subsector}"
        questions = self.questionnaire_data.get("questions", {}).get(question_key, [])

        for q in questions:
            if q["id"] == question_id and "options" in q:
                return q["options"]

        return []

    def format_proposal_summary(self, proposal: Dict[str, Any]) -> str:
        """Formatea un resumen de la propuesta para presentar al usuario"""
        client_info = proposal["client_info"]
        project_details = proposal["project_details"]
        treatment = proposal["recommended_treatment"]
        costs = proposal["cost_estimation"]
        roi = proposal["roi_analysis"]

        # Formatear tecnologías recomendadas
        technologies = []
        for stage, details in treatment.items():
            if details and "tecnologias" in details:
                for tech in details["tecnologias"]:
                    technologies.append(f"{tech} ({stage})")

        # Crear una introduccion personalizada
        intro = f"¡Excelente, {client_info['name']}! Gracias por completar el cuestionario. Basado en tus respuestas, he preparado una propuesta personalizada para tu proyecto de tratamiento de aguas residuales en el sector {client_info['sector']} - {client_info['subsector']}."

        # Definir todo el formato previamente
        capex_total = format(costs["capex"]["total"], ",.2f")
        opex_anual = format(costs["opex"]["total_anual"], ",.2f")
        opex_mensual = format(costs["opex"]["total_mensual"], ",.2f")
        ahorro_anual = format(roi["ahorro_anual"], ",.2f")
        periodo_recuperacion = format(roi["periodo_recuperacion"], ".1f")
        roi_5_anos = format(roi["roi_5_anos"], ".1f")

        # Preparar secciones para tratamientos
        pretratamiento = (
            ", ".join(treatment["pretratamiento"]["tecnologias"])
            if "pretratamiento" in treatment
            and treatment["pretratamiento"]
            and "tecnologias" in treatment["pretratamiento"]
            else "No requerido"
        )
        primario = (
            ", ".join(treatment["primario"]["tecnologias"])
            if "primario" in treatment
            and treatment["primario"]
            and "tecnologias" in treatment["primario"]
            else "No requerido"
        )
        secundario = (
            ", ".join(treatment["secundario"]["tecnologias"])
            if "secundario" in treatment
            and treatment["secundario"]
            and "tecnologias" in treatment["secundario"]
            else "No requerido"
        )
        terciario = (
            ", ".join(treatment["terciario"]["tecnologias"])
            if "terciario" in treatment
            and treatment["terciario"]
            and "tecnologias" in treatment["terciario"]
            else "No requerido"
        )

        # Preparar objetivos
        objetivos_principales = (
            ("• " + "\n• ".join(project_details["objectives"]))
            if project_details.get("objectives")
            else "No especificados"
        )
        objetivos_reuso = (
            ("• " + "\n• ".join(project_details["reuse_objectives"]))
            if project_details.get("reuse_objectives")
            else "No especificados"
        )

        # Usar un string template simple sin formato complejo
        summary = f"""
        {intro}

        **RESUMEN DE LA PROPUESTA DE HYDROUS**

        **DATOS DEL PROYECTO**
        - Cliente: {client_info['name']}
        - Ubicación: {client_info['location']}
        - Sector: {client_info['sector']} - {client_info['subsector']}
        - Flujo de agua a tratar: {project_details.get('flow_rate', 'No especificado')}

        **OBJETIVOS PRINCIPALES**
        {objetivos_principales}

        **OBJETIVOS DE REÚSO**
        {objetivos_reuso}

        **SOLUCIÓN TECNOLÓGICA RECOMENDADA**
        - **Pretratamiento**: {pretratamiento}
        - **Tratamiento primario**: {primario}
        - **Tratamiento secundario**: {secundario}
        - **Tratamiento terciario**: {terciario}

        **ANÁLISIS ECONÓMICO**
        - Inversión inicial estimada: ${capex_total} USD
        - Costo operativo anual: ${opex_anual} USD/año
        - Costo operativo mensual: ${opex_mensual} USD/mes

        **RETORNO DE INVERSIÓN**
        - Ahorro anual estimado: ${ahorro_anual} USD/año
        - Periodo de recuperación: {periodo_recuperacion} años
        - ROI a 5 años: {roi_5_anos}%

        **BENEFICIOS AMBIENTALES**
        - Reducción de la huella hídrica de tu operación
        - Disminución de la descarga de contaminantes al medio ambiente
        - Cumplimiento con normativas ambientales vigentes
        - Contribución a la sostenibilidad del recurso hídrico

        **PRÓXIMOS PASOS**
        ¿Te gustaría recibir una propuesta detallada por correo electrónico? ¿O prefieres programar una reunión con nuestros especialistas para revisar en detalle esta recomendación y resolver cualquier duda específica?

        También puedo responder cualquier pregunta adicional que tengas sobre la solución propuesta.
        """
        return summary


# Instancia global del servicio
questionnaire_service = QuestionnaireService()
