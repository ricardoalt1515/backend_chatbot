# app/models/questionnaire_state.py
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import re


class QuestionnaireState(BaseModel):
    """Modelo mejorado para mantener el estado del cuestionario y el contexto de la conversación"""

    # Sector y subsector seleccionados
    sector: Optional[str] = None
    subsector: Optional[str] = None

    # Índice de la pregunta actual
    current_question_index: int = 0

    # Respuestas almacenadas
    answers: Dict[str, Any] = Field(default_factory=dict)

    # Preguntas que se han presentado
    presented_questions: List[str] = Field(default_factory=list)

    # Entidades importantes extraídas
    key_entities: Dict[str, Any] = Field(default_factory=dict)

    # Si el cuestionario está completo
    is_complete: bool = False

    def update_answer(self, question_id: str, answer: Any) -> None:
        """Actualiza la respuesta a una pregunta específica con validación"""
        # Normalizar y validar la respuesta según el tipo de pregunta
        normalized_answer = self._normalize_answer(question_id, answer)

        # Guardar respuesta normalizada
        self.answers[question_id] = normalized_answer

        # Extraer entidades clave basadas en la pregunta
        self._extract_key_entity(question_id, normalized_answer)

    def _normalize_answer(self, question_id: str, answer: str) -> str:
        """Normaliza la respuesta según el tipo de pregunta"""
        if not answer:
            return answer

        # Normalización específica según tipo de pregunta
        if question_id == "costo_agua":
            # Extraer valores numéricos
            match = re.search(r"(\d+(?:\.\d+)?)", str(answer))
            if match:
                # Intentar detectar la unidad o usar MXN/m³ por defecto
                unit_match = re.search(r"([A-Za-z]+\/[A-Za-z\d³]+)", str(answer))
                unit = unit_match.group(1) if unit_match else "MXN/m³"
                return f"{match.group(1)} {unit}"

        elif (
            question_id == "cantidad_agua_consumida"
            or question_id == "cantidad_agua_residual"
        ):
            # Extraer valores numéricos y posibles unidades (m³/día, lps, etc.)
            num_match = re.search(r"(\d+(?:\.\d+)?)", str(answer))
            unit_match = re.search(
                r"(m³\/día|m3\/día|lps|l\/s)", str(answer), re.IGNORECASE
            )

            if num_match:
                value = num_match.group(1)
                unit = unit_match.group(1) if unit_match else "m³/día"
                return f"{value} {unit}"

        elif question_id == "num_personas":
            # Asegurarse de que es un número o un rango
            try:
                # Si es un número entero
                int(answer)
                return answer
            except (ValueError, TypeError):
                # Si es un rango textual, intentar extraer
                range_match = re.search(r"(\d+).*?(\d+)", str(answer))
                if range_match:
                    return f"{range_match.group(1)}-{range_match.group(2)}"

        # Para preguntas de opción múltiple, normalizar a la opción correcta
        elif question_id == "objetivo_principal":
            # Mapeo de patrones comunes a opciones estándar
            options = {
                "cump": "Cumplimiento normativo",
                "norm": "Cumplimiento normativo",
                "reduc": "Reducción de la huella ambiental",
                "ambient": "Reducción de la huella ambiental",
                "ecolog": "Reducción de la huella ambiental",
                "huella": "Reducción de la huella ambiental",
                "ahorr": "Ahorro de costos/Proyecto de retorno de inversión",
                "cost": "Ahorro de costos/Proyecto de retorno de inversión",
                "roi": "Ahorro de costos/Proyecto de retorno de inversión",
                "inver": "Ahorro de costos/Proyecto de retorno de inversión",
                "retorno": "Ahorro de costos/Proyecto de retorno de inversión",
                "disponi": "Mayor disponibilidad de agua",
                "escasez": "Mayor disponibilidad de agua",
            }

            # Buscar coincidencias en el texto de respuesta
            lower_answer = str(answer).lower()
            for pattern, option in options.items():
                if pattern in lower_answer:
                    return option

            # Si no coincide con ningún patrón, verificar si es un número de opción
            try:
                option_num = int(answer.strip())
                if option_num == 1:
                    return "Cumplimiento normativo"
                elif option_num == 2:
                    return "Reducción de la huella ambiental"
                elif option_num == 3:
                    return "Ahorro de costos/Proyecto de retorno de inversión"
                elif option_num == 4:
                    return "Mayor disponibilidad de agua"
            except (ValueError, TypeError):
                pass

        elif question_id == "objetivo_reuso":
            # Extraer múltiples objetivos si están enumerados
            reuse_options = [
                "riego",
                "áreas verdes",
                "jardines",
                "sanitario",
                "baños",
                "inodoros",
                "industrial",
                "procesos",
                "producción",
                "cumplimiento",
                "normativo",
                "regulación",
            ]

            selected_options = []
            lower_answer = str(answer).lower()

            for option in reuse_options:
                if option in lower_answer:
                    if "riego" in option or "verde" in option or "jardín" in option:
                        selected_options.append("Uso en riego de áreas verdes")
                    elif (
                        "sanitario" in option or "baño" in option or "inodoro" in option
                    ):
                        selected_options.append("Reúso en sanitarios")
                    elif (
                        "industrial" in option
                        or "proceso" in option
                        or "producción" in option
                    ):
                        selected_options.append("Reúso en procesos industriales")
                    elif (
                        "cumplimiento" in option
                        or "normativo" in option
                        or "regulación" in option
                    ):
                        selected_options.append("Cumplimiento normativo")

            # También verificar números de opciones
            num_matches = re.findall(r"\b[1-5]\b", answer)
            for num in num_matches:
                option_num = int(num)
                if option_num == 1:
                    selected_options.append("Uso en riego de áreas verdes")
                elif option_num == 2:
                    selected_options.append("Reúso en sanitarios")
                elif option_num == 3:
                    selected_options.append("Reúso en procesos industriales")
                elif option_num == 4:
                    selected_options.append("Cumplimiento normativo")

            # Eliminar duplicados
            selected_options = list(set(selected_options))

            if selected_options:
                return selected_options

        elif question_id == "descarga_actual":
            # Mapeo de patrones comunes a opciones estándar
            options = {
                "alcant": "Alcantarillado",
                "drenaje": "Alcantarillado",
                "munici": "Alcantarillado",
                "río": "Cuerpo de agua natural (Ríos, Lagunas, Esteros o Subsuelo)",
                "lake": "Cuerpo de agua natural (Ríos, Lagunas, Esteros o Subsuelo)",
                "laguna": "Cuerpo de agua natural (Ríos, Lagunas, Esteros o Subsuelo)",
                "estero": "Cuerpo de agua natural (Ríos, Lagunas, Esteros o Subsuelo)",
                "natural": "Cuerpo de agua natural (Ríos, Lagunas, Esteros o Subsuelo)",
                "subsuelo": "Cuerpo de agua natural (Ríos, Lagunas, Esteros o Subsuelo)",
                "pozo": "Cuerpo de agua natural (Ríos, Lagunas, Esteros o Subsuelo)",
            }

            # Buscar coincidencias en el texto de respuesta
            lower_answer = str(answer).lower()
            for pattern, option in options.items():
                if pattern in lower_answer:
                    return option

            # Verificar si es un número de opción
            try:
                option_num = int(answer.strip())
                if option_num == 1:
                    return "Alcantarillado"
                elif option_num == 2:
                    return "Cuerpo de agua natural (Ríos, Lagunas, Esteros o Subsuelo)"
            except (ValueError, TypeError):
                pass

        # Por defecto, devuelve la respuesta original
        return str(answer)

    def _extract_key_entity(self, question_id: str, answer: str) -> None:
        """Extrae entidades clave de las respuestas y las almacena"""
        # Mapeo de preguntas a entidades clave
        entity_mappings = {
            "nombre_empresa": "company_name",
            "ubicacion": "location",
            "cantidad_agua_consumida": "water_consumption",
            "cantidad_agua_residual": "wastewater_volume",
            "costo_agua": "water_cost",
            "presupuesto": "budget",
            "num_personas": "personnel",
            "objetivo_principal": "main_objective",
            "objetivo_reuso": "reuse_objective",
            "descarga_actual": "current_discharge",
        }

        # Si existe un mapeo para esta pregunta, guardar como entidad clave
        if question_id in entity_mappings:
            self.key_entities[entity_mappings[question_id]] = answer

        # También almacenar información sobre sector/subsector
        if question_id == "sector" and answer:
            self.sector = answer

        if question_id == "subsector" and answer:
            self.subsector = answer

    def get_context_summary(self) -> str:
        """Genera un resumen detallado del contexto actual para incluir en el prompt"""
        summary_parts = []

        # Añadir entidades clave con etiquetas
        for entity_name, value in self.key_entities.items():
            if value:
                # Traducir nombres de entidades a español para mejor contexto
                entity_label = self._get_entity_label(entity_name)
                summary_parts.append(f"{entity_label}: {value}")

        # Añadir sector/subsector si están definidos
        if self.sector:
            summary_parts.append(f"Sector: {self.sector}")
        if self.subsector:
            summary_parts.append(f"Subsector: {self.subsector}")

        # Añadir respuestas a preguntas clave que no estén ya como entidades
        for q_id, answer in self.answers.items():
            # Evitar duplicar entidades ya incluidas
            if not any(
                entity_name
                for entity_name, entity_key in entity_mappings.items()
                if q_id == entity_name
            ):
                # Obtener nombre legible de la pregunta
                q_label = self._get_question_label(q_id)
                summary_parts.append(f"{q_label}: {answer}")

        return "\n".join(summary_parts)

    def _get_entity_label(self, entity_name: str) -> str:
        """Convierte nombres de entidades internas a etiquetas legibles"""
        labels = {
            "company_name": "Nombre de la empresa",
            "location": "Ubicación",
            "water_consumption": "Consumo de agua",
            "wastewater_volume": "Volumen de aguas residuales",
            "water_cost": "Costo del agua",
            "budget": "Presupuesto",
            "personnel": "Personal",
            "main_objective": "Objetivo principal",
            "reuse_objective": "Objetivo de reúso",
            "current_discharge": "Descarga actual",
        }
        return labels.get(entity_name, entity_name)

    def _get_question_label(self, question_id: str) -> str:
        """Convierte IDs de preguntas a etiquetas legibles"""
        labels = {
            "nombre_empresa": "Nombre de la empresa",
            "ubicacion": "Ubicación",
            "costo_agua": "Costo del agua",
            "cantidad_agua_consumida": "Consumo de agua",
            "cantidad_agua_residual": "Generación de aguas residuales",
            "num_personas": "Número de personas",
            "objetivo_principal": "Objetivo principal",
            "objetivo_reuso": "Objetivo de reúso",
            "descarga_actual": "Descarga actual",
            "restricciones": "Restricciones",
            "presupuesto": "Presupuesto estimado",
            "tiempo_proyecto": "Plazo del proyecto",
            "parametros_agua": "Parámetros del agua",
        }
        return labels.get(question_id, question_id)
