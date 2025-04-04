# app/services/questionnaire_service.py
import logging
from typing import Optional, List, Dict, Any

from app.models.conversation_state import ConversationState

# Importa la estructura de datos del cuestionario
from app.services.questionnaire_data import QUESTIONNAIRE_STRUCTURE

logger = logging.getLogger("hydrous")


class QuestionnaireService:

    def __init__(self):
        self.structure = QUESTIONNAIRE_STRUCTURE
        self.all_questions = (
            self._flatten_questions()
        )  # Diccionario plano para búsqueda rápida por ID

    def _flatten_questions(self) -> Dict[str, Dict[str, Any]]:
        """Crea un diccionario plano de todas las preguntas por ID."""
        flat_questions = {}
        # Añadir preguntas iniciales
        for q in self.structure.get("initial_questions", []):
            flat_questions[q["id"]] = q
        # Añadir preguntas de sector/subsector
        for sector, subsectors in self.structure.get(
            "sector_questionnaires", {}
        ).items():
            for subsector, questions in subsectors.items():
                for q in questions:
                    flat_questions[q["id"]] = q
        return flat_questions

    def get_initial_greeting(self) -> str:
        """Devuelve el saludo inicial."""
        return self.structure.get("initial_greeting", "¡Bienvenido!")

    def get_initial_question_id(self) -> Optional[str]:
        """Devuelve el ID de la primera pregunta inicial."""
        initial_questions = self.structure.get("initial_questions", [])
        return initial_questions[0]["id"] if initial_questions else None

    def get_question(self, question_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene los detalles de una pregunta por su ID."""
        return self.all_questions.get(question_id)

    def _determine_questionnaire_path(self, state: ConversationState) -> List[str]:
        """Determina la secuencia de IDs de preguntas basado en el sector/subsector."""
        path = [
            q["id"] for q in self.structure.get("initial_questions", [])
        ]  # Empezar con iniciales

        sector = state.selected_sector
        subsector = state.selected_subsector

        if sector and subsector:
            try:
                sector_questions = self.structure["sector_questionnaires"][sector][
                    subsector
                ]
                path.extend([q["id"] for q in sector_questions])
            except KeyError:
                logger.warning(
                    f"No se encontró cuestionario para Sector: {sector}, Subsector: {subsector}. Usando genérico si existe."
                )
                # Podrías tener una sección "Otro" o "Genérico" como fallback
                generic_questions = (
                    self.structure["sector_questionnaires"]
                    .get(sector, {})
                    .get("Otro", [])
                )
                path.extend([q["id"] for q in generic_questions])

        return path

    def get_next_question_id(self, state: ConversationState) -> Optional[str]:
        """
        Determina el ID de la siguiente pregunta a realizar, actualizando la ruta si es necesario.
        Devuelve None si el cuestionario ha terminado.
        """
        # Si la ruta aún no se ha definido (p.ej., después de las preguntas iniciales)
        if (
            not state.questionnaire_path
            and state.selected_sector
            and state.selected_subsector
        ):
            state.questionnaire_path = self._determine_questionnaire_path(state)
            logger.info(
                f"Ruta del cuestionario determinada para {state.selected_sector}/{state.selected_subsector}: {state.questionnaire_path}"
            )
            # Si después de determinar la ruta, la pregunta actual es la última inicial,
            # necesitamos avanzar a la primera de la ruta específica del sector.
            if state.current_question_id in [
                q["id"] for q in self.structure.get("initial_questions", [])
            ]:
                # Buscar la primera pregunta que NO esté en las iniciales
                first_sector_q = next(
                    (
                        qid
                        for qid in state.questionnaire_path
                        if qid
                        not in [
                            q["id"] for q in self.structure.get("initial_questions", [])
                        ]
                    ),
                    None,
                )
                if first_sector_q:
                    # La siguiente pregunta es la primera específica del sector
                    state.current_question_id = state.questionnaire_path[
                        state.questionnaire_path.index(first_sector_q) - 1
                    ]  # Truco para que get_next devuelva la correcta
                    # return first_sector_q
                else:  # Solo había preguntas iniciales?
                    state.is_complete = True
                    return None

        # Si aún no hay ruta (falta sector/subsector), seguir con iniciales si las hay
        if not state.questionnaire_path:
            initial_q_ids = [
                q["id"] for q in self.structure.get("initial_questions", [])
            ]
            if state.current_question_id is None:
                return initial_q_ids[0] if initial_q_ids else None
            try:
                current_index = initial_q_ids.index(state.current_question_id)
                if current_index + 1 < len(initial_q_ids):
                    return initial_q_ids[current_index + 1]
                else:
                    # Se terminaron las iniciales pero aún no hay sector/subsector?
                    # Podríamos re-preguntar o manejar este caso. Por ahora, asumimos que no pasa.
                    logger.warning(
                        "Se terminaron las preguntas iniciales sin definir sector/subsector."
                    )
                    return None
            except ValueError:
                return initial_q_ids[0] if initial_q_ids else None  # Fallback

        # Si ya tenemos una ruta definida, obtener la siguiente pregunta de esa ruta
        next_id = state.get_next_question_in_path()

        # Manejar preguntas dependientes (ej. preguntar detalles si no se subió archivo)
        while next_id:
            question_details = self.get_question(next_id)
            if question_details and "depends_on" in question_details:
                dependency = question_details["depends_on"]
                dep_id = dependency["id"]
                expected_value = dependency.get("value")
                value_is_negative = dependency.get(
                    "value_is_negative", False
                )  # Chequear si no se dio la respuesta esperada

                actual_answer = state.collected_data.get(dep_id)

                condition_met = False
                if value_is_negative:
                    # Condición se cumple si la respuesta NO fue la esperada o no se dio
                    # (Simplificado: considera 'no', 'false', None, '' como negativos)
                    negative_responses = ["no", "false", "", None, False]
                    # También considerar si la respuesta fue un número para opción múltiple
                    dep_question = self.get_question(dep_id)
                    if dep_question and dep_question["type"] == "multiple_choice":
                        try:
                            # Si la opción negativa es la última (ej. 'No tengo análisis')
                            if actual_answer is not None and int(actual_answer) == len(
                                dep_question["options"]
                            ):
                                condition_met = True
                        except (ValueError, TypeError):
                            pass  # No era número o no era opción múltiple válida

                    if (
                        str(actual_answer).lower() in negative_responses
                        or actual_answer is None
                    ):
                        condition_met = True

                elif expected_value is not None:
                    # Condición se cumple si la respuesta FUE la esperada
                    if str(actual_answer) == str(
                        expected_value
                    ):  # Comparar como strings por simplicidad
                        condition_met = True

                if condition_met:
                    # La dependencia se cumple, esta es la siguiente pregunta
                    return next_id
                else:
                    # La dependencia NO se cumple, saltar esta pregunta y buscar la siguiente
                    state.current_question_id = (
                        next_id  # Marcarla como "saltada" para avanzar
                    )
                    next_id = state.get_next_question_in_path()
                    continue  # Volver al inicio del while con el nuevo next_id
            else:
                # No es una pregunta dependiente, esta es la siguiente
                return next_id

        # Si salimos del bucle sin encontrar next_id, el cuestionario terminó
        if not next_id:
            state.is_complete = True
        return None

    def process_answer(self, question_id: str, user_input: str) -> Any:
        """Procesa la respuesta del usuario (validación simple)."""
        question = self.get_question(question_id)
        if not question:
            return user_input  # No se pudo validar

        q_type = question.get("type")

        if q_type == "multiple_choice" or q_type == "conditional_multiple_choice":
            try:
                choice_index = int(user_input.strip()) - 1
                options = question.get("options")
                # Para condicionales, las opciones dependen de la respuesta anterior
                if q_type == "conditional_multiple_choice":
                    # Necesitaríamos el estado para saber la respuesta anterior y obtener las opciones correctas
                    # Por simplicidad ahora, asumimos que las opciones ya están cargadas correctamente
                    # En una implementación real, get_question debería resolver esto basado en el estado
                    pass  # Aquí iría la lógica para cargar opciones dinámicas si no se hizo antes

                if options and 0 <= choice_index < len(options):
                    return options[choice_index]  # Devolver el texto de la opción
                else:
                    # Si el número no es válido, devolver el input original
                    logger.warning(
                        f"Respuesta numérica '{user_input}' inválida para pregunta {question_id}. Usando texto."
                    )
                    return user_input.strip()
            except ValueError:
                # No fue un número, devolver el input original (podría ser el texto de la opción)
                return user_input.strip()
        elif q_type == "multiple_open":
            # Podríamos intentar parsear si el usuario dio respuestas separadas por comas, etc.
            # Por ahora, solo devolvemos el texto tal cual.
            return user_input.strip()
        else:  # open, document_upload, etc.
            return user_input.strip()

    def format_question_for_display(self, question_details: Dict[str, Any]) -> str:
        """Formatea una pregunta para mostrarla al usuario."""
        if not question_details:
            return "Hubo un problema al cargar la siguiente pregunta."

        q_text = question_details.get("text", "")
        q_type = question_details.get("type")
        q_explanation = question_details.get("explanation", "")

        # Manejar texto dinámico (ej. para preguntas condicionales)
        # Necesitaríamos el estado para reemplazar {sector}, etc.
        # q_text = q_text.format(...) # Requeriría pasar el estado aquí

        formatted_string = f"**PREGUNTA:** {q_text}\n"

        if q_type == "multiple_choice" or q_type == "conditional_multiple_choice":
            options = question_details.get("options", [])
            # Para condicionales, las opciones pueden venir de 'conditions'
            # Aquí asumimos que ya están resueltas en 'options' por simplicidad
            if options:
                formatted_string += (
                    "Por favor, elige una opción (responde solo con el número):\n"
                )
                for i, option in enumerate(options):
                    formatted_string += f"{i+1}. {option}\n"
            else:
                logger.warning(
                    f"Pregunta de opción múltiple {question_details['id']} sin opciones definidas!"
                )
                formatted_string += "(Error: Opciones no disponibles)\n"

        elif q_type == "multiple_open":
            sub_questions = question_details.get("sub_questions", [])
            if sub_questions:
                formatted_string += "Por favor, proporciona los siguientes datos:\n"
                for sub_q in sub_questions:
                    formatted_string += (
                        f"- {sub_q['label']} ______\n"  # Indicar que se espera input
                    )
            else:
                logger.warning(
                    f"Pregunta multiple_open {question_details['id']} sin sub-preguntas!"
                )

        elif q_type == "document_upload":
            formatted_string += "Puedes subir el archivo relevante ahora.\n"

        # Añadir explicación
        if q_explanation:
            formatted_string += f"\n*¿Por qué preguntamos esto?* 🤔\n*{q_explanation}*"

        return formatted_string.strip()


# Crear una instancia global para ser usada por otros servicios/rutas
questionnaire_service = QuestionnaireService()
