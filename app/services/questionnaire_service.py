# app/services/questionnaire_service.py
import logging
from typing import Optional, List, Dict, Any, cast  # Añadir cast si usas mypy
import copy  # Importar copy para no modificar la estructura original

from app.models.conversation_state import ConversationState

# Importa la estructura de datos del cuestionario
from app.services.questionnaire_data import QUESTIONNAIRE_STRUCTURE

logger = logging.getLogger("hydrous")


class QuestionnaireService:

    def __init__(self):
        self.structure = QUESTIONNAIRE_STRUCTURE
        # Diccionario plano para búsqueda rápida por ID. Se crea una sola vez.
        self.all_questions_base: Dict[str, Dict[str, Any]] = self._flatten_questions()
        logger.info(
            f"Servicio de Cuestionario inicializado con {len(self.all_questions_base)} preguntas base cargadas."
        )

    def _flatten_questions(self) -> Dict[str, Dict[str, Any]]:
        """Crea un diccionario plano de todas las preguntas por ID desde la estructura."""
        flat_questions = {}
        # Añadir preguntas iniciales
        for q in self.structure.get("initial_questions", []):
            if "id" in q:
                flat_questions[q["id"]] = q
            else:
                logger.error(
                    f"Pregunta inicial sin ID encontrada: {q.get('text', 'N/A')}"
                )

        # Añadir preguntas de sector/subsector
        for sector, subsectors in self.structure.get(
            "sector_questionnaires", {}
        ).items():
            for subsector, questions in subsectors.items():
                if not isinstance(questions, list):
                    logger.error(
                        f"Estructura inválida para {sector}/{subsector}. Se esperaba una lista de preguntas, se encontró {type(questions)}"
                    )
                    continue
                for q in questions:
                    if "id" in q:
                        flat_questions[q["id"]] = q
                    else:
                        logger.error(
                            f"Pregunta sin ID encontrada en {sector}/{subsector}: {q.get('text', 'N/A')}"
                        )
        return flat_questions

    def get_initial_greeting(self) -> str:
        """Devuelve el saludo inicial."""
        return self.structure.get("initial_greeting", "¡Bienvenido!")

    def get_initial_question_id(self) -> Optional[str]:
        """Devuelve el ID de la primera pregunta inicial."""
        initial_questions = self.structure.get("initial_questions", [])
        return (
            initial_questions[0]["id"]
            if initial_questions and "id" in initial_questions[0]
            else None
        )

    def get_question(
        self, question_id: str, state: Optional[ConversationState] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene los detalles de una pregunta por su ID, resolviendo
        opciones condicionales y texto dinámico si se proporciona el estado.
        Devuelve una COPIA del diccionario de la pregunta para evitar efectos secundarios.
        """
        question_base = self.all_questions_base.get(question_id)
        if not question_base:
            logger.error(f"No se encontró la pregunta base con ID: {question_id}")
            return None

        # Crear una copia profunda para trabajar sobre ella y no modificar la base
        question_details = copy.deepcopy(question_base)

        q_type = question_details.get("type")
        q_text_template = question_details.get("text", "")  # Guardar plantilla original

        # --- Resolución dinámica si se proporciona el estado ---
        if state:
            # 1. Resolver texto dinámico (placeholders como {sector})
            try:
                # Crear contexto para formateo: incluir attrs de state y key_entities
                format_context = state.dict(
                    exclude_none=True
                )  # Excluir None para evitar errores si falta algo
                format_context.update(state.key_entities)
                # Usar format_map para manejar claves faltantes sin error
                question_details["text"] = q_text_template.format_map(format_context)
            except KeyError as e:
                logger.warning(
                    f"Clave faltante '{e}' al formatear texto para pregunta {question_id}. Texto original: '{q_text_template}'"
                )
                # Mantener el texto original con placeholder si falla el formateo
                question_details["text"] = q_text_template

            # 2. Resolver opciones condicionales
            if q_type == "conditional_multiple_choice":
                depends_on_key = question_details.get("depends_on_key")
                conditions = question_details.get("conditions", {})

                if depends_on_key and conditions:
                    # Obtener el valor de la clave de dependencia del estado
                    dependency_value = getattr(state, depends_on_key, None)

                    if dependency_value and dependency_value in conditions:
                        # Encontramos las opciones! Las asignamos a la clave 'options'
                        question_details["options"] = conditions[dependency_value]
                        logger.debug(
                            f"Opciones resueltas para {question_id} basadas en {depends_on_key}='{dependency_value}': {question_details['options']}"
                        )
                    else:
                        # No se encontró valor o no hay opciones para ese valor
                        logger.warning(
                            f"No se pudieron resolver opciones condicionales para {question_id}. Clave: '{depends_on_key}', Valor en estado: '{dependency_value}'. Opciones disponibles en 'conditions': {list(conditions.keys())}"
                        )
                        question_details["options"] = (
                            []
                        )  # Dejar vacío para que format_question muestre error
                else:
                    logger.error(
                        f"Pregunta condicional {question_id} mal configurada: falta 'depends_on_key' o 'conditions'."
                    )
                    question_details["options"] = []
            # Asegurarse que 'options' existe incluso si no es condicional (para evitar KeyErrors)
            elif "options" not in question_details and q_type == "multiple_choice":
                question_details["options"] = (
                    []
                )  # Inicializar si falta en una no condicional
                logger.warning(
                    f"Pregunta {question_id} de tipo multiple_choice no tenía clave 'options'."
                )

        # Devolver la copia modificada (o la original si no hubo estado/cambios)
        return question_details

    def _determine_questionnaire_path(self, state: ConversationState) -> List[str]:
        """Determina la secuencia de IDs de preguntas basado en el sector/subsector."""
        # Empezar siempre con las preguntas iniciales
        path = [
            q["id"] for q in self.structure.get("initial_questions", []) if "id" in q
        ]

        sector = state.selected_sector
        subsector = state.selected_subsector

        if sector and subsector:
            try:
                sector_data = self.structure.get("sector_questionnaires", {}).get(
                    sector, {}
                )
                subsector_questions = sector_data.get(subsector, [])

                if not isinstance(subsector_questions, list):
                    logger.error(
                        f"Esperaba lista de preguntas para {sector}/{subsector}, obtuve {type(subsector_questions)}. Usando fallback 'Otro'."
                    )
                    subsector_questions = sector_data.get(
                        "Otro", []
                    )  # Intentar fallback "Otro" dentro del sector

                path.extend([q["id"] for q in subsector_questions if "id" in q])
                logger.info(
                    f"Ruta determinada para {sector}/{subsector}. Total preguntas: {len(path)}"
                )

            except Exception as e:  # Captura más general por si acaso
                logger.error(
                    f"Error al determinar ruta para Sector: {sector}, Subsector: {subsector}. Error: {e}",
                    exc_info=True,
                )
                # Intentar usar fallback genérico si existe
                generic_questions = (
                    self.structure.get("sector_questionnaires", {})
                    .get(sector, {})
                    .get("Otro", [])
                )
                if generic_questions:
                    logger.warning(
                        f"Usando cuestionario 'Otro' para sector {sector} como fallback."
                    )
                    path.extend([q["id"] for q in generic_questions if "id" in q])
                else:
                    logger.error(
                        f"No se encontró cuestionario ni fallback 'Otro' para {sector}/{subsector}."
                    )
        elif sector:
            logger.warning(
                f"Sector '{sector}' seleccionado, pero falta subsector para determinar ruta completa."
            )
            # La ruta contendrá solo las preguntas iniciales hasta que se seleccione subsector
        else:
            logger.debug("Aún no se selecciona sector/subsector para determinar ruta.")

        return path

    def get_next_question_id(self, state: ConversationState) -> Optional[str]:
        """
        Determina el ID de la siguiente pregunta a realizar, actualizando la ruta si es necesario.
        Devuelve None si el cuestionario ha terminado.
        """
        # 1. Determinar/Actualizar la ruta si es necesario (si ya tenemos sector Y subsector)
        if (
            not state.questionnaire_path
            and state.selected_sector
            and state.selected_subsector
        ):
            state.questionnaire_path = self._determine_questionnaire_path(state)
            # Si la ruta sigue vacía después de esto, algo falló en la determinación
            if not state.questionnaire_path:
                logger.error(
                    f"No se pudo determinar una ruta de cuestionario válida para {state.selected_sector}/{state.selected_subsector}"
                )
                state.is_complete = True  # Marcar como completo para evitar bucle
                return None

        # 2. Obtener el ID de la siguiente pregunta basado en la ruta actual o las iniciales
        if state.questionnaire_path:
            # Ya tenemos una ruta completa (iniciales + específicas)
            next_id = state.get_next_question_in_path()
        else:
            # Aún estamos en las preguntas iniciales porque falta sector/subsector
            initial_q_ids = [
                q["id"]
                for q in self.structure.get("initial_questions", [])
                if "id" in q
            ]
            if not initial_q_ids:
                logger.error("No hay preguntas iniciales definidas.")
                state.is_complete = True
                return None

            if state.current_question_id is None:
                next_id = initial_q_ids[0]  # La primera inicial
            else:
                try:
                    current_index = initial_q_ids.index(state.current_question_id)
                    if current_index + 1 < len(initial_q_ids):
                        next_id = initial_q_ids[
                            current_index + 1
                        ]  # La siguiente inicial
                    else:
                        # Se terminaron las iniciales, pero aún no hay ruta completa (falta sector/subsector)
                        # Esto significa que la última pregunta inicial (probablemente INIT_2) no logró
                        # establecer el subsector necesario para definir la ruta.
                        # Deberíamos quedarnos aquí o manejarlo? Por ahora, devolvemos None.
                        logger.warning(
                            f"Se completaron preguntas iniciales, pero falta sector/subsector para continuar. Última pregunta: {state.current_question_id}"
                        )
                        next_id = None
                        # No marcar como completo aún, esperar a que el usuario responda a INIT_2
                        # state.is_complete = True # NO marcar completo aquí
                except ValueError:
                    logger.warning(
                        f"ID actual '{state.current_question_id}' no encontrado en preguntas iniciales. Volviendo a la primera."
                    )
                    next_id = initial_q_ids[0]  # Fallback a la primera inicial

        # 3. Manejar preguntas dependientes (saltar si no se cumple la condición)
        skipped_questions = (
            set()
        )  # Para evitar bucles infinitos si hay dependencias circulares
        original_next_id = next_id  # Guardar el ID original por si necesitamos volver

        while next_id and next_id not in skipped_questions:
            # --- PASAR EL ESTADO AQUÍ para que get_question pueda resolver ---
            question_details = self.get_question(next_id, state)
            # ---------------------------------------------------------------

            if not question_details:
                logger.error(
                    f"get_next_question_id: No se pudieron obtener detalles para el ID '{next_id}'. Saltando."
                )
                # Intentar avanzar en la ruta manualmente si get_question falló
                state.current_question_id = next_id  # Marcar como visitado/fallido
                next_id = state.get_next_question_in_path()
                continue

            if "depends_on" in question_details:
                dependency = question_details["depends_on"]
                dep_id = dependency.get("id")
                expected_value = dependency.get("value")
                value_is_negative = dependency.get("value_is_negative", False)
                value_contains = dependency.get("value_contains")

                if not dep_id:
                    logger.error(
                        f"Dependencia mal configurada en pregunta {next_id}: falta 'id'. Saltando dependencia."
                    )
                    return next_id  # Asumir que se debe preguntar

                actual_answer = state.collected_data.get(dep_id)
                logger.debug(
                    f"Chequeando dependencia para {next_id}: depende de {dep_id} (respuesta: '{actual_answer}'). Condición: neg={value_is_negative}, val='{expected_value}', contains='{value_contains}'"
                )

                condition_met = False
                if value_is_negative:
                    # Condición se cumple si la respuesta es considerada "negativa"
                    negative_responses = [
                        "no",
                        "false",
                        "",
                        None,
                        False,
                        "0",
                    ]  # Añadir '0'
                    # Caso especial: opción múltiple donde 'No' es la última opción
                    dep_question_details = self.get_question(
                        dep_id, state
                    )  # Obtener detalles CON estado
                    if (
                        dep_question_details
                        and dep_question_details.get("type")
                        in ["multiple_choice", "yes_no"]
                        and dep_question_details.get("options")
                    ):
                        options = dep_question_details["options"]
                        try:
                            # Si la respuesta fue el número de la última opción O el texto de la última opción (case-insensitive)
                            if str(actual_answer) == str(len(options)) or (
                                isinstance(actual_answer, str)
                                and actual_answer.lower() == options[-1].lower()
                            ):
                                condition_met = True
                                logger.debug(
                                    f"Dependencia negativa: respuesta '{actual_answer}' coincide con última opción."
                                )
                        except (ValueError, TypeError, IndexError):
                            pass  # Ignorar si la conversión o acceso falla

                    # Chequeo general de respuesta negativa
                    if (
                        not condition_met
                        and str(actual_answer).lower() in negative_responses
                    ):
                        condition_met = True
                        logger.debug(
                            f"Dependencia negativa: respuesta '{actual_answer}' considerada negativa."
                        )

                elif value_contains is not None:
                    # Condición se cumple si la respuesta (string) contiene el valor esperado
                    if (
                        isinstance(actual_answer, str)
                        and value_contains.lower() in actual_answer.lower()
                    ):
                        condition_met = True
                        logger.debug(
                            f"Dependencia contains: respuesta '{actual_answer}' contiene '{value_contains}'."
                        )
                elif expected_value is not None:
                    # Condición se cumple si la respuesta es exactamente la esperada (comparar como strings)
                    if str(actual_answer) == str(expected_value):
                        condition_met = True
                        logger.debug(
                            f"Dependencia value: respuesta '{actual_answer}' es igual a '{expected_value}'."
                        )

                # Decisión final sobre la dependencia
                if condition_met:
                    logger.debug(
                        f"Condición de dependencia para {next_id} CUMPLIDA. Se preguntará."
                    )
                    return next_id  # La dependencia se cumple, esta es la siguiente pregunta
                else:
                    logger.info(
                        f"Condición de dependencia para {next_id} NO CUMPLIDA. Saltando esta pregunta."
                    )
                    skipped_questions.add(
                        next_id
                    )  # Añadir a saltadas para evitar bucle
                    state.current_question_id = (
                        next_id  # Marcarla como "visitada" para avanzar en la ruta
                    )
                    next_id = (
                        state.get_next_question_in_path()
                    )  # Buscar la siguiente en la ruta
                    continue  # Volver al inicio del while con el nuevo next_id
            else:
                # No es una pregunta dependiente, esta es la siguiente
                return next_id

        # Si salimos del bucle (next_id es None o caímos en bucle detectado)
        if next_id in skipped_questions:
            logger.error(
                f"Detectado posible bucle de dependencia alrededor de la pregunta {original_next_id}. Terminando cuestionario."
            )
            state.is_complete = True
            return None

        # Si next_id es None porque se terminó la ruta
        if not next_id and not state.is_complete:
            logger.info(
                f"Se ha alcanzado el final de la ruta del cuestionario. Marcando como completo. Última pregunta procesada: {state.current_question_id}"
            )
            state.is_complete = True

        return None  # El cuestionario ha terminado

    def process_answer(self, question_id: str, user_input: str) -> Any:
        """Procesa la respuesta del usuario, intentando convertirla al tipo esperado."""
        # Obtener detalles base (no necesita estado para procesar la respuesta en sí)
        question = self.get_question(question_id)  # Llamada SIN estado aquí es OK
        if not question:
            logger.warning(
                f"process_answer: No se encontró pregunta con ID {question_id}. Devolviendo input crudo."
            )
            return user_input.strip()

        q_type = question.get("type")
        cleaned_input = user_input.strip()

        if (
            q_type == "multiple_choice"
            or q_type == "conditional_multiple_choice"
            or q_type == "yes_no"
        ):
            options = question.get("options", [])
            if (
                not options
            ):  # Esto puede pasar si las opciones condicionales no se resolvieron
                logger.warning(
                    f"process_answer: No hay opciones definidas/resueltas para la pregunta {question_id}. Devolviendo input crudo: '{cleaned_input}'"
                )
                return cleaned_input

            # 1. Intentar coincidencia por número
            try:
                choice_index = int(cleaned_input) - 1
                if 0 <= choice_index < len(options):
                    logger.debug(
                        f"process_answer: Coincidencia por número {cleaned_input} -> {options[choice_index]}"
                    )
                    return options[choice_index]  # Devolver el texto de la opción
            except ValueError:
                pass  # No era un número, intentar por texto

            # 2. Intentar coincidencia por texto (case-insensitive)
            for option_text in options:
                if cleaned_input.lower() == option_text.lower():
                    logger.debug(
                        f"process_answer: Coincidencia por texto '{cleaned_input}' -> {option_text}"
                    )
                    return option_text  # Devolver el texto original de la opción

            # 3. Si no coincide ni número ni texto, devolver crudo (podría ser 'Otro')
            logger.debug(
                f"process_answer: Sin coincidencia para '{cleaned_input}' en opciones de {question_id}. Devolviendo crudo."
            )
            return cleaned_input

        elif q_type == "multiple_open":
            # Podríamos intentar parsear si el usuario dio respuestas separadas, pero es complejo.
            # Por ahora, devolver el texto tal cual. El LLM tendrá que interpretarlo al generar propuesta.
            return cleaned_input
        # Añadir manejo para otros tipos si es necesario (ej: numérico, fecha)
        # elif q_type == "numeric":
        #     try: return float(cleaned_input)
        #     except ValueError: return cleaned_input # Fallback
        else:  # open, document_upload, confirmation, etc.
            return cleaned_input

    def format_question_for_display(
        self, question_details: Optional[Dict[str, Any]]
    ) -> str:
        """
        Formatea una pregunta para mostrarla al usuario.
        Asume que question_details ya tiene el texto y las opciones resueltas
        por una llamada previa a get_question(..., state=...).
        """
        if not question_details:
            logger.error("format_question_for_display recibió None")
            return "Hubo un problema al cargar la siguiente pregunta. [FQFD01]"

        q_text = question_details.get("text", "[Texto de pregunta faltante]")
        q_type = question_details.get("type")
        q_explanation = question_details.get("explanation", "")
        options = question_details.get(
            "options", []
        )  # Obtener opciones (ya deberían estar resueltas)
        confirmation_text = question_details.get(
            "confirmation_text"
        )  # Para tipo 'confirmation'

        # Empezar con el texto de la pregunta principal
        formatted_string = f"**PREGUNTA:** {q_text}\n"

        # Añadir elementos específicos por tipo
        if (
            q_type == "multiple_choice"
            or q_type == "conditional_multiple_choice"
            or q_type == "yes_no"
        ):
            if options:  # Verificar si la lista de opciones resuelta no está vacía
                formatted_string += (
                    "\nPor favor, elige una opción (responde solo con el número):\n"
                )
                for i, option in enumerate(options):
                    formatted_string += f"{i+1}. {option}\n"
            else:
                # Loguear error pero mostrar mensaje más genérico al usuario
                q_id = question_details.get("id", "N/A")
                logger.error(
                    f"format_question_for_display: Pregunta {q_id} de tipo opción múltiple SIN opciones válidas para mostrar."
                )
                formatted_string += "\n*(Error interno: No se pudieron cargar las opciones para esta pregunta. Por favor, contacta a soporte.)*\n"

        elif q_type == "multiple_open":
            sub_questions = question_details.get("sub_questions", [])
            if sub_questions:
                formatted_string += "\nPor favor, proporciona los siguientes datos (puedes separarlos por comas o en líneas diferentes):\n"
                for sub_q in sub_questions:
                    label = sub_q.get("label", "[dato faltante]")
                    formatted_string += (
                        f"- {label}\n"  # No poner '____' para no confundir
                    )
            else:
                q_id = question_details.get("id", "N/A")
                logger.warning(
                    f"format_question_for_display: Pregunta multiple_open {q_id} sin sub-preguntas definidas."
                )

        elif q_type == "document_upload":
            formatted_string += "\n*Puedes usar el botón de adjuntar 📎 para subir el archivo relevante ahora.*\n"

        elif q_type == "confirmation":
            if confirmation_text:
                formatted_string += f"\n{confirmation_text}\n"
            # Este tipo no suele necesitar input del usuario, pero sí explicación.

        # Añadir explicación si existe
        if q_explanation:
            formatted_string += f"\n*¿Por qué preguntamos esto?* 🤔\n*{q_explanation}*"

        return formatted_string.strip()


# Crear una instancia global para ser usada por otros servicios/rutas
# Esto asegura que el diccionario aplanado se cree una sola vez.
questionnaire_service = QuestionnaireService()
