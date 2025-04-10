# app/services/proposal_service.py
import logging
import os
import re
from typing import Dict, Any, Optional

from app.models.conversation import Conversation

# Importar ai_service si queremos que LLM refine secciones (Opcional)
# from app.services.ai_service import ai_service

logger = logging.getLogger("hydrous")


class ProposalService:

    def __init__(self):
        # Cargar plantilla base de la propuesta
        self.template_string = self._load_template()
        # Cargar valores típicos (puedes expandir esto)
        self.typical_values = self._load_typical_values()

    def _load_template(self) -> str:
        """Carga la plantilla de propuesta desde el archivo."""
        try:
            template_path = os.path.join(
                os.path.dirname(__file__), "../prompts/Format Proposal.txt"
            )
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    # Leer y reemplazar saltos de línea múltiples para evitar dobles espacios
                    content = f.read()
                    # content = re.sub(r'\n\s*\n', '\n', content) # Opcional: limpiar saltos
                    return content
            else:
                logger.error(
                    "Plantilla de propuesta (Format Proposal.txt) no encontrada."
                )
                # Devolver una plantilla básica como fallback
                return """
# Propuesta de Tratamiento de Agua - Hydrous Management Group

**Importante Descargo de Responsabilidad:**
[...]

## 1. Introducción a Hydrous Management Group
[...]

## 2. Antecedentes del Proyecto
**Información del Cliente:**
- Cliente: [CLIENT_NAME]
- Ubicación: [LOCATION]
- Industria: [INDUSTRY_SECTOR] / [INDUSTRY_SUBSECTOR]
- Fuente de Agua: [WATER_SOURCE]
- Consumo de Agua Actual: [WATER_CONSUMPTION]
- Generación de Aguas Residuales Actual: [WASTEWATER_GENERATION]
- Sistema de Tratamiento Existente: [EXISTING_SYSTEM_STATUS]

## 3. Objetivo del Proyecto
- Objetivo Principal: [MAIN_OBJECTIVE]
- Objetivos de Reúso/Descarga: [REUSE_OBJECTIVES]

## 4. Supuestos Clave y Comparación con Estándares
| Parámetro | Aguas Residuales Crudas (Proporcionadas) | Estándar Industria Similar | Objetivo Efluente |
|---|---|---|---|
| SST (mg/L) | [TSS_VALUE] | [TSS_STANDARD] | [TSS_GOAL] |
| DQO (mg/L) | [COD_VALUE] | [COD_STANDARD] | [COD_GOAL] |
| DBO (mg/L) | [BOD_VALUE] | [BOD_STANDARD] | [BOD_GOAL] |
| pH         | [PH_VALUE]  | [PH_STANDARD]  | [PH_GOAL]  |
| TDS (mg/L) | [TDS_VALUE] | [TDS_STANDARD] | [TDS_GOAL] |
| GyA (mg/L) | [FOG_VALUE] | [FOG_STANDARD] | [FOG_GOAL] |
*Nota: [N/A] indica dato no proporcionado. Se usarán valores estándar para diseño preliminar.*

## 5. Diseño del Proceso y Alternativas de Tratamiento
[DISEÑO_PROCESO_TEXTO]

## 6. Equipos Sugeridos y Dimensionamiento
[EQUIPOS_DIMENSIONES_TEXTO]

## 7. CAPEX y OPEX Estimados
**CAPEX (Inversión Inicial):**
- Rango Estimado: [BUDGET_RANGE] USD (Basado en información preliminar)
- Desglose Detallado: [PENDIENTE - Requiere ingeniería de detalle]

**OPEX (Costo Operativo Mensual):**
- Rango Estimado: [OPEX_RANGE] USD/mes
- Desglose Detallado: [PENDIENTE - Requiere análisis energético y de consumibles]

## 8. Análisis de Retorno de Inversión (ROI)
[ANALISIS_ROI_TEXTO]

## 9. Exhibit de Preguntas y Respuestas
[RESUMEN_Q&A_TEXTO]
"""
        except Exception as e:
            logger.error(
                f"Error al cargar la plantilla de propuesta: {e}", exc_info=True
            )
            return "Error: No se pudo cargar la plantilla."

    def _load_typical_values(self) -> Dict[str, Any]:
        """Carga o define valores típicos por sector/subsector."""
        # Esto podría venir de un archivo JSON o estar codificado aquí
        # Ejemplo muy básico
        return {
            "Comercial": {
                "Hotel": {
                    "TSS_STANDARD": "100-300",
                    "COD_STANDARD": "400-800",
                    "BOD_STANDARD": "200-400",
                    "PH_STANDARD": "6-8",
                    "TDS_STANDARD": "500-1000",
                    "FOG_STANDARD": "20-60",
                    "TSS_GOAL": "<50",
                    "COD_GOAL": "<100",
                    "BOD_GOAL": "<30",
                    "PH_GOAL": "6.5-8.5",
                    "TDS_GOAL": "<600 (reúso WC/riego)",
                    "FOG_GOAL": "<15",
                },
                "Restaurante": {
                    "TSS_STANDARD": "300-600",
                    "COD_STANDARD": "800-2500",
                    "BOD_STANDARD": "400-1200",
                    "PH_STANDARD": "6-9",
                    "TDS_STANDARD": "500-1500",
                    "FOG_STANDARD": "100-300",
                    "TSS_GOAL": "<100 (desc. alcant.)",
                    "COD_GOAL": "<300",
                    "BOD_GOAL": "<150",
                    "PH_GOAL": "6.5-9",
                    "TDS_GOAL": "N/A",
                    "FOG_GOAL": "<100",
                },
                # Añadir otros subsectores comerciales
            },
            "Industrial": {
                "Metal/Automotriz": {
                    "TSS_STANDARD": "100-500",
                    "COD_STANDARD": "500-2000",
                    "BOD_STANDARD": "200-800",
                    "PH_STANDARD": "5-10",
                    "TDS_STANDARD": "1000-4000",
                    "FOG_STANDARD": "50-500",  # Muy variable
                    "TSS_GOAL": "<50 (desc. alcant.)",
                    "COD_GOAL": "<200",
                    "BOD_GOAL": "<100",
                    "PH_GOAL": "6.5-9",
                    "TDS_GOAL": "N/A",
                    "FOG_GOAL": "<30 (o menos)",
                },
                # Añadir otros subsectores industriales
            },
            # Añadir Municipal, Residencial
            "_default": {  # Valores por defecto si no se encuentra el sector
                "TSS_STANDARD": "100-400",
                "COD_STANDARD": "300-800",
                "BOD_STANDARD": "150-400",
                "PH_STANDARD": "6-9",
                "TDS_STANDARD": "500-1500",
                "FOG_STANDARD": "20-100",
                "TSS_GOAL": "<50",
                "COD_GOAL": "<150",
                "BOD_GOAL": "<50",
                "PH_GOAL": "6.5-8.5",
                "TDS_GOAL": "N/A",
                "FOG_GOAL": "<20",
            },
        }

    def _get_typical_value(
        self, sector: Optional[str], subsector: Optional[str], param_key: str
    ) -> str:
        """Obtiene un valor típico de la estructura."""
        try:
            if sector and subsector:
                val = (
                    self.typical_values.get(sector, {})
                    .get(subsector, {})
                    .get(param_key)
                )
                if val:
                    return str(val)
            # Fallback a sector general o default
            if sector:
                val = (
                    self.typical_values.get(sector, {})
                    .get("_default", {})
                    .get(param_key)
                )
                if val:
                    return str(val)
            # Fallback a default general
            return str(self.typical_values.get("_default", {}).get(param_key, "[N/D]"))
        except Exception:
            return "[N/D]"  # No disponible

    def _format_data_for_template(
        self, collected_data: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepara los datos para ser insertados en la plantilla."""
        data = {}
        sector = metadata.get("selected_sector")
        subsector = metadata.get("selected_subsector")

        # Mapeo de IDs de preguntas a claves de plantilla (AJUSTAR IDs según questionnaire_data.py)
        # Usamos .get con default para manejar respuestas faltantes
        data["CLIENT_NAME"] = collected_data.get("INIT_0", "[Nombre no proporcionado]")
        # Asumir ID de ubicación según sector/subsector o usar uno genérico si no cambia
        location_id = "IAB_1"  # Ejemplo, ajustar según tu estructura real de IDs
        if sector == "Comercial" and subsector == "Hotel":
            location_id = "CHT_1"
        elif sector == "Industrial" and subsector == "Metal/Automotriz":
            location_id = "IMA_1"
        # ... añadir más mapeos de ID de ubicación si son diferentes ...
        data["LOCATION"] = collected_data.get(
            location_id, "[Ubicación no proporcionada]"
        )

        data["INDUSTRY_SECTOR"] = sector or "[Sector no especificado]"
        data["INDUSTRY_SUBSECTOR"] = subsector or "[Subsector no especificado]"

        # IDs para fuente, costo, consumo, etc. (ajustar según tus IDs reales)
        data["WATER_SOURCE"] = collected_data.get(
            "CHT_11", "[Fuente no especificada]"
        )  # Ejemplo Hotel
        data["WATER_COST"] = collected_data.get("CHT_2", "[Costo no especificado]")
        data["WATER_CONSUMPTION"] = collected_data.get(
            "CHT_3", "[Consumo no especificado]"
        )
        data["WASTEWATER_GENERATION"] = collected_data.get(
            "CHT_4", "[Generación no especificada]"
        )
        # ... mapear el resto de los datos comunes y específicos ...
        data["EXISTING_SYSTEM_BOOL"] = collected_data.get("CHT_18", "No")
        data["EXISTING_SYSTEM_DESC"] = collected_data.get(
            "CHT_19", ""
        )  # Asumiendo que esta es la descripción
        data["MAIN_OBJECTIVE"] = collected_data.get(
            "CHT_14", "[Objetivo no especificado]"
        )
        data["REUSE_OBJECTIVES"] = collected_data.get(
            "CHT_15", "[Objetivo reúso no especificado]"
        )
        data["BUDGET_RANGE"] = collected_data.get(
            "CHT_21", "[Presupuesto no especificado]"
        )

        # Estado del sistema existente
        data["EXISTING_SYSTEM_STATUS"] = (
            "Sí" if str(data["EXISTING_SYSTEM_BOOL"]).lower() == "sí" else "No"
        )
        if data["EXISTING_SYSTEM_STATUS"] == "Sí" and data["EXISTING_SYSTEM_DESC"]:
            data["EXISTING_SYSTEM_STATUS"] += f": {data['EXISTING_SYSTEM_DESC']}"

        # Datos de Calidad de Agua (usar N/A si no se proporcionó)
        data["TSS_VALUE"] = collected_data.get("CHT_8_TSS", "[N/A]")  # Ejemplo Hotel
        data["COD_VALUE"] = collected_data.get("CHT_8_COD", "[N/A]")
        data["BOD_VALUE"] = collected_data.get("CHT_8_BOD", "[N/A]")
        data["PH_VALUE"] = collected_data.get("CHT_8_PH", "[N/A]")
        data["TDS_VALUE"] = collected_data.get(
            "CHT_8_TDS_HVAC", "[N/A]"
        )  # Ejemplo específico
        data["FOG_VALUE"] = collected_data.get("CHT_8_FOG", "[N/A]")

        # Obtener valores estándar y metas
        data["TSS_STANDARD"] = self._get_typical_value(
            sector, subsector, "TSS_STANDARD"
        )
        data["COD_STANDARD"] = self._get_typical_value(
            sector, subsector, "COD_STANDARD"
        )
        data["BOD_STANDARD"] = self._get_typical_value(
            sector, subsector, "BOD_STANDARD"
        )
        data["PH_STANDARD"] = self._get_typical_value(sector, subsector, "PH_STANDARD")
        data["TDS_STANDARD"] = self._get_typical_value(
            sector, subsector, "TDS_STANDARD"
        )
        data["FOG_STANDARD"] = self._get_typical_value(
            sector, subsector, "FOG_STANDARD"
        )
        data["TSS_GOAL"] = self._get_typical_value(sector, subsector, "TSS_GOAL")
        data["COD_GOAL"] = self._get_typical_value(sector, subsector, "COD_GOAL")
        data["BOD_GOAL"] = self._get_typical_value(sector, subsector, "BOD_GOAL")
        data["PH_GOAL"] = self._get_typical_value(sector, subsector, "PH_GOAL")
        data["TDS_GOAL"] = self._get_typical_value(sector, subsector, "TDS_GOAL")
        data["FOG_GOAL"] = self._get_typical_value(sector, subsector, "FOG_GOAL")

        # Placeholders para secciones que generará el LLM o lógica más compleja
        data["DISEÑO_PROCESO_TEXTO"] = (
            "[PENDIENTE - Se requiere análisis detallado o consulta a IA]"
        )
        data["EQUIPOS_DIMENSIONES_TEXTO"] = (
            "[PENDIENTE - Se requiere dimensionamiento basado en flujo y carga]"
        )
        data["OPEX_RANGE"] = "[Rango OPEX pendiente]"
        data["ANALISIS_ROI_TEXTO"] = (
            "[Análisis ROI pendiente - requiere estimaciones CAPEX/OPEX y ahorros]"
        )
        data["RESUMEN_Q&A_TEXTO"] = (
            "[Resumen de preguntas y respuestas clave de la consulta]"  # Podríamos construir esto
        )

        logger.debug(f"Datos formateados para plantilla: {data}")
        return data

    def _fill_template(self, template_data: Dict[str, Any]) -> str:
        """Rellena la plantilla con los datos usando reemplazo simple."""
        filled_template = self.template_string
        for key, value in template_data.items():
            placeholder = f"[{key}]"  # Buscar placeholder [KEY]
            # Convertir valor a string para reemplazo, manejar listas/dicts básicos
            if isinstance(value, list):
                str_value = ", ".join(map(str, value)) if value else "[No especificado]"
            elif isinstance(value, dict):
                str_value = json.dumps(value) if value else "[No especificado]"
            else:
                str_value = str(value) if value is not None else "[No especificado]"

            # Usar regex para reemplazar insensible a mayúsculas/minúsculas y manejar espacios
            try:
                # Escapar caracteres especiales en el placeholder para regex
                escaped_placeholder = re.escape(placeholder)
                # Reemplazo insensible a mayúsculas
                filled_template = re.sub(
                    escaped_placeholder, str_value, filled_template, flags=re.IGNORECASE
                )
            except re.error as re_err:
                logger.error(f"Error de Regex reemplazando '{placeholder}': {re_err}")
                # Fallback a reemplazo simple si regex falla
                filled_template = filled_template.replace(placeholder, str_value)

        # Limpiar placeholders restantes que no se encontraron
        filled_template = re.sub(
            r"\[[A-Z_]{3,}\]", "[Dato no disponible]", filled_template
        )

        return filled_template

    async def _refine_section_with_llm(self, section_name: str, prompt: str) -> str:
        """Llama al LLM para generar/refinar una sección específica (Función Auxiliar Opcional)."""
        logger.debug(f"Llamando a LLM para refinar sección: {section_name}")
        try:
            # Necesitaríamos importar y usar ai_service aquí
            # response = await ai_service._call_llm_api([{"role":"user", "content":prompt}], max_tokens=300, temperature=0.5)
            # return response
            return (
                f"[{section_name} - Contenido generado por IA pendiente]"  # Placeholder
            )
        except Exception as e:
            logger.warning(
                f"Fallo al llamar a LLM para refinar sección '{section_name}': {e}"
            )
            return f"[{section_name} - Error al generar contenido]"

    def _generate_qa_summary(self, collected_data: Dict[str, Any]) -> str:
        """Genera un resumen de Q&A a partir de los datos recolectados."""
        summary = "A continuación se resumen las preguntas clave y respuestas proporcionadas:\n\n"
        # Importar questionnaire_service aquí para obtener textos de preguntas
        try:
            from app.services.questionnaire_service import questionnaire_service

            for q_id, answer in collected_data.items():
                q_details = questionnaire_service.get_question_details(q_id)
                q_text = q_details.get("text", q_id) if q_details else q_id
                # Limpiar placeholders del texto de la pregunta si los hubiera
                q_text = re.sub(r"{.*?}", "", q_text).strip()
                summary += f"- **P: {q_text}**\n"
                summary += f"  R: {answer}\n\n"
        except ImportError:
            logger.error("No se pudo importar questionnaire_service para generar Q&A.")
            summary += "[Error al generar resumen Q&A]\n"
        except Exception as e:
            logger.error(f"Error generando resumen Q&A: {e}")
            summary += "[Error al generar resumen Q&A]\n"

        return summary

    # --- Función Principal ---
    async def generate_proposal_text(self, conversation: Conversation) -> str:
        """Genera propuesta completa y personalizada usando LLM."""

        # Obtener datos recopilados
        metadata = conversation.metadata
        collected_data = metadata.get("collected_data", {})
        sector = metadata.get("selected_sector", "No especificado")
        subsector = metadata.get("selected_subsector", "No especificado")

        # Extraer datos específicos para simplificar el prompt
        client_name = collected_data.get("INIT_0", "Cliente")  # Nombre
        location = collected_data.get("INIT_1", "No especificada")  # Ubicación
        water_cost = collected_data.get("INIT_2", "No especificado")  # Costo de agua
        water_consumption = collected_data.get(
            "INIT_3", "No especificado"
        )  # Consumo de agua
        wastewater = collected_data.get("INIT_4", "No especificado")  # Aguas residuales
        people = collected_data.get("INIT_5", "No especificado")  # Personas

        # Crear un resumen estructurado de los datos críticos
        data_summary = f"""
# DATOS CRÍTICOS DEL CLIENTE Y PROYECTO
    - Nombre: {client_name}
    - Ubicación: {location}
    - Sector: {sector}
    - Subsector: {subsector}
    - Costo del agua: {water_cost}
    - Consumo de agua: {water_consumption}
    - Generación de aguas residuales: {wastewater}
    - Número de personas: {people}
    """

        # Incluir todos los datos recopilados para referencia
        all_data = "\n\n# DATOS ADICIONALES RECOPILADOS\n"
        for key, value in collected_data.items():
            question = questionnaire_service.get_question_details(key)
            question_text = question.get("text", key) if question else key
            all_data += f"- {question_text}: {value}\n"

        # Crear prompt detallado y EXTREMADAMENTE específico
        prompt = f"""
# INSTRUCCIÓN: CREAR PROPUESTA TÉCNICA-ECONÓMICA DE TRATAMIENTO DE AGUA COMPLETA

    Como experto ingeniero en tratamiento de agua, crea una propuesta técnica y económica COMPLETA, DETALLADA y PERSONALIZADA.
    Esta propuesta DEBE incluir TODOS los elementos solicitados, con cálculos exactos, dimensionamiento preciso y estimaciones económicas realistas.

## DATOS DEL CLIENTE:
    {data_summary}

## DATOS ADICIONALES:
    {all_data}

## INSTRUCCIONES CRÍTICAS:
    1. **NO INCLUIR PLACEHOLDERS** - Reemplaza TODOS los campos como [XX,XXX], [Dimensiones], etc., con valores reales calculados. TODO valor debe ser específico para este cliente.

    2. **USAR VALORES ESPECÍFICOS DEL CLIENTE** - Usa explícitamente todos los datos proporcionados sobre consumo, costo y volumen.

    3. **CALCULAR VALORES NO PROPORCIONADOS** - Si faltan datos, calcula valores típicos para este sector/subsector específico.

    4. **CREAR DIMENSIONAMIENTO DETALLADO** - Calcula y especifica capacidades, dimensiones y especificaciones técnicas exactas.

    5. **REALIZAR ANÁLISIS FINANCIERO COMPLETO**:
    - CAPEX detallado con costos por componente
    - OPEX mensual completo (químicos, energía, mano de obra)
    - ROI específico con tiempo de recuperación de inversión basado en ahorro de agua
    - Ahorro anual proyectado basado en el costo del agua proporcionado
    
    6. **INCLUIR DISEÑO TÉCNICO COMPLETO** - No sólo listar componentes, sino explicar cómo se conectan y por qué se seleccionaron.

    7. **AÑADIR RESUMEN EJECUTIVO** - Al inicio, presenta un resumen conciso de los beneficios clave.

## ESTRUCTURA OBLIGATORIA:
    1. Introducción a Hydrous Management Group
    2. Resumen Ejecutivo (beneficios clave)
    3. Información del Proyecto (todos los datos del cliente)
    4. Objetivos del Proyecto (adaptados a lo proporcionado)
    5. Solución Técnica Propuesta (detallada, con dimensiones específicas)
    6. Equipamiento y Materiales (marcas, modelos, especificaciones)
    7. Análisis Financiero (CAPEX, OPEX, ROI - todos con cifras exactas)
    8. Cronograma de Implementación
    9. Conclusiones y Recomendaciones

    IMPORTANTE: Esta propuesta será entregada como PDF oficial y no debe contener ningún placeholder o información genérica.
    """

        from app.services.ai_service import ai_service

        try:
            # Usar un modelo potente con suficiente contexto y más tokens para generar contenido completo
            messages = [{"role": "user", "content": prompt}]
            proposal_text = await ai_service._call_llm_api(
                messages,
                max_tokens=4000,  # Aumentar tokens para respuesta más completa
                temperature=0.2,  # Reducir temperatura para respuestas más deterministas
            )

            # Verificar calidad de la respuesta
            if not proposal_text or len(proposal_text) < 1000:
                logger.error(
                    f"Respuesta LLM demasiado corta: {len(proposal_text)} caracteres"
                )
                return "Error: Propuesta generada incompleta. Por favor, intente nuevamente."

            # Añadir marcador para procesamiento posterior
            proposal_text = (
                proposal_text.strip()
                + "\n\n[PROPOSAL_COMPLETE: Propuesta lista para PDF]"
            )
            return proposal_text

        except Exception as e:
            logger.error(f"Error generando propuesta con LLM: {e}", exc_info=True)
            return f"Error: Falló la generación de propuesta. Detalles: {str(e)[:100]}"


# Instancia global
proposal_service = ProposalService()
