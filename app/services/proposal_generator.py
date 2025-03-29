# app/services/proposal_generator.py
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import re
from app.models.conversation import Conversation

logger = logging.getLogger("hydrous")


class ProposalGenerator:
    """Servicio para generar propuestas formales basadas en la información recopilada"""

    def __init__(self, format_template: Dict[str, Any] = None):
        """Inicializa el generador con la plantilla de formato"""
        self.format_template = format_template or self._get_default_template()

    def generate_proposal_instructions(self, conversation: Conversation) -> str:
        """Genera instrucciones específicas para la propuesta basada en la información recopilada"""
        # Recopilar información clave
        client_info = self._extract_client_info(conversation)
        water_info = self._extract_water_info(conversation)
        objectives = self._extract_objectives(conversation)
        tech_params = self._extract_technical_parameters(conversation)

        # Crear instrucciones específicas siguiendo el formato de propuesta
        instructions = f"""
INSTRUCCIONES PARA GENERAR LA PROPUESTA FORMAL:

Debes generar una propuesta profesional y completa utilizando EXACTAMENTE el siguiente formato:

# 📌 **Hydrous Management Group -- Propuesta de Tratamiento de Aguas Residuales**

## **Información del Cliente**
- **Cliente:** {client_info.get('name', '[Nombre del Cliente]')}
- **Ubicación:** {client_info.get('location', '[Ubicación]')}
- **Industria:** {client_info.get('sector', '[Sector Industrial]')}
- **Subsector:** {client_info.get('subsector', '[Subsector]')}

## **Consumo y Costos Actuales**
- **Consumo de Agua:** {water_info.get('consumption', '[Consumo]')}
- **Generación de Aguas Residuales:** {water_info.get('wastewater', '[Volumen]')}
- **Costo Actual del Agua:** {water_info.get('cost', '[Costo]')}

## **Objetivos del Proyecto**
{self._format_objectives(objectives)}

## **Parámetros de Diseño y Comparación con Estándares Industriales**
Crea una tabla comparativa con los siguientes parámetros. Para los valores que no tengas, usa estimaciones típicas de la industria {client_info.get('sector', 'específica')}:

| **Parámetro** | **Valor Actual** | **Estándar Industrial** | **Objetivo de Tratamiento** |
|---------------|------------------|-------------------------|----------------------------|
| DQO (mg/L)    | {tech_params.get('dqo', '[Valor]')} | [Rango típico] | [Objetivo] |
| DBO (mg/L)    | {tech_params.get('dbo', '[Valor]')} | [Rango típico] | [Objetivo] |
| SST (mg/L)    | {tech_params.get('sst', '[Valor]')} | [Rango típico] | [Objetivo] |
| pH            | {tech_params.get('ph', '[Valor]')} | [Rango típico] | [Objetivo] |

## **Diseño del Proceso y Alternativas de Tratamiento**
Presenta tecnologías recomendadas con este formato:

| **Etapa de Tratamiento** | **Tecnología Recomendada** | **Alternativa Viable** | **Justificación** |
|--------------------------|----------------------------|------------------------|-------------------|
| Pretratamiento          | [Tecnología] | [Alternativa] | [Razón de selección] |
| Tratamiento Primario    | [Tecnología] | [Alternativa] | [Razón de selección] |
| Tratamiento Secundario  | [Tecnología] | [Alternativa] | [Razón de selección] |
| Tratamiento Terciario   | [Tecnología] | [Alternativa] | [Razón de selección] |

Para la selección de tecnologías, considera:
- El sector {client_info.get('sector', 'industrial')} específicamente {client_info.get('subsector', '')}
- El volumen de agua residual ({water_info.get('wastewater', 'X m³/día')})
- Los objetivos del cliente, principalmente {objectives[0] if objectives else 'tratamiento eficiente'}

## **Equipamiento Sugerido y Dimensionamiento**
Proporciona una tabla de equipamiento con estas columnas:

| **Equipo** | **Capacidad** | **Dimensiones** | **Observaciones** |
|------------|---------------|-----------------|-------------------|
| [Equipo 1] | [Capacidad]   | [Dimensiones]   | [Notas importantes] |
| [Equipo 2] | [Capacidad]   | [Dimensiones]   | [Notas importantes] |

## **Estimación de CAPEX y OPEX**

### CAPEX (Inversión Inicial)
| **Componente** | **Rango Estimado (USD)** |
|----------------|-----------------------------|
| Obra Civil     | [Rango] |
| Equipamiento   | [Rango] |
| Instalación    | [Rango] |
| **Total**      | **[Rango Total]** |

### OPEX (Costos Operativos Mensuales)
| **Concepto** | **Estimado Mensual (USD)** |
|--------------|----------------------------|
| Energía      | [Estimado] |
| Químicos     | [Estimado] |
| Mano de Obra | [Estimado] |
| Mantenimiento| [Estimado] |
| **Total**    | **[Total Mensual]** |

## **Análisis de Retorno de Inversión (ROI)**
| **Concepto** | **Actual** | **Con Sistema de Tratamiento** | **Ahorro Anual** |
|--------------|------------|--------------------------------|------------------|
| Costo de Agua| [Actual]   | [Proyectado]                   | [Diferencia]     |
| Costo de Descarga | [Actual] | [Proyectado]                | [Diferencia]     |
| **Total**    | **[Suma]** | **[Suma]**                     | **[Ahorro Total]**|

ROI estimado: **[X años]** (Inversión total ÷ Ahorro anual)

## **Próximos Pasos Recomendados**
1. [Paso 1]
2. [Paso 2]
3. [Paso 3]

## **Anexo: Resumen de Información Proporcionada**
{self._summarize_provided_information(conversation)}

IMPORTANTE: La propuesta debe ser realista y basada EXCLUSIVAMENTE en la información proporcionada durante nuestra conversación. Para los datos que no tengas, usa valores típicos para la industria {client_info.get('sector', '')} {client_info.get('subsector', '')}, pero indícalo claramente.

Al finalizar la propuesta, incluye exactamente esta línea:
[PROPOSAL_COMPLETE: Esta propuesta está lista para descargarse como PDF]
"""
        return instructions

    def _extract_client_info(self, conversation: Conversation) -> Dict[str, Any]:
        """Extrae información del cliente de la conversación"""
        info = {
            "name": "Cliente",
            "location": "No especificada",
            "sector": conversation.questionnaire_state.sector or "Industrial",
            "subsector": conversation.questionnaire_state.subsector or "",
        }

        # Extrae de key_entities
        if "company_name" in conversation.questionnaire_state.key_entities:
            info["name"] = conversation.questionnaire_state.key_entities["company_name"]

        if "location" in conversation.questionnaire_state.key_entities:
            info["location"] = conversation.questionnaire_state.key_entities["location"]

        # Si no se encuentra en key_entities, buscar en respuestas
        if (
            info["name"] == "Cliente"
            and "nombre_empresa" in conversation.questionnaire_state.answers
        ):
            info["name"] = conversation.questionnaire_state.answers["nombre_empresa"]

        if (
            info["location"] == "No especificada"
            and "ubicacion" in conversation.questionnaire_state.answers
        ):
            info["location"] = conversation.questionnaire_state.answers["ubicacion"]

        # Buscar en mensajes como último recurso
        if info["name"] == "Cliente" or info["location"] == "No especificada":
            for msg in conversation.messages:
                if msg.role == "user":
                    # Buscar nombre de empresa
                    if info["name"] == "Cliente":
                        company_match = re.search(
                            r"(?:empresa|compañía|proyecto|cliente|nombre)[\s:]+([a-zA-Z0-9\s]+)",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if company_match:
                            info["name"] = company_match.group(1).strip()

                    # Buscar ubicación
                    if info["location"] == "No especificada":
                        location_match = re.search(
                            r"(?:ubicación|ubicacion|localización|ciudad)[\s:]+([a-zA-Z0-9\s,]+)",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if location_match:
                            info["location"] = location_match.group(1).strip()

        return info

    def _extract_water_info(self, conversation: Conversation) -> Dict[str, Any]:
        """Extrae información sobre agua y costos"""
        info = {
            "consumption": "No especificado",
            "wastewater": "No especificado",
            "cost": "No especificado",
        }

        # Extrae de key_entities
        if "water_consumption" in conversation.questionnaire_state.key_entities:
            info["consumption"] = conversation.questionnaire_state.key_entities[
                "water_consumption"
            ]

        if "wastewater_volume" in conversation.questionnaire_state.key_entities:
            info["wastewater"] = conversation.questionnaire_state.key_entities[
                "wastewater_volume"
            ]

        if "water_cost" in conversation.questionnaire_state.key_entities:
            info["cost"] = conversation.questionnaire_state.key_entities["water_cost"]

        # Busca también en respuestas
        answers = conversation.questionnaire_state.answers
        if "cantidad_agua_consumida" in answers and (
            info["consumption"] == "No especificado"
        ):
            info["consumption"] = answers["cantidad_agua_consumida"]

        if "cantidad_agua_residual" in answers and (
            info["wastewater"] == "No especificado"
        ):
            info["wastewater"] = answers["cantidad_agua_residual"]

        if "costo_agua" in answers and (info["cost"] == "No especificado"):
            info["cost"] = answers["costo_agua"]

        # Buscar en mensajes como último recurso
        if (
            info["consumption"] == "No especificado"
            or info["wastewater"] == "No especificado"
            or info["cost"] == "No especificado"
        ):
            for msg in conversation.messages:
                if msg.role == "user":
                    # Buscar consumo de agua
                    if info["consumption"] == "No especificado":
                        consumption_match = re.search(
                            r"(?:consumo|gasto|uso).*?agua.*?(\d+[\.,]?\d*\s*(?:m3|m³|lps|litros|l\/s))",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if consumption_match:
                            info["consumption"] = consumption_match.group(1).strip()

                    # Buscar generación de aguas residuales
                    if info["wastewater"] == "No especificado":
                        wastewater_match = re.search(
                            r"(?:residual|efluente|descarga).*?(\d+[\.,]?\d*\s*(?:m3|m³|lps|litros|l\/s))",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if wastewater_match:
                            info["wastewater"] = wastewater_match.group(1).strip()

                    # Buscar costo de agua
                    if info["cost"] == "No especificado":
                        cost_match = re.search(
                            r"(?:costo|precio|tarifa).*?agua.*?(\d+[\.,]?\d*\s*(?:\$|MXN|USD|EUR)\/(?:m3|m³))",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if cost_match:
                            info["cost"] = cost_match.group(1).strip()

        return info

    def _extract_objectives(self, conversation: Conversation) -> List[str]:
        """Extrae los objetivos del proyecto"""
        objectives = []

        # Buscar en key_entities
        if "main_objective" in conversation.questionnaire_state.key_entities:
            objectives.append(
                conversation.questionnaire_state.key_entities["main_objective"]
            )

        if "reuse_objective" in conversation.questionnaire_state.key_entities:
            reuse_obj = conversation.questionnaire_state.key_entities["reuse_objective"]
            if isinstance(reuse_obj, list):
                objectives.extend(reuse_obj)
            else:
                objectives.append(reuse_obj)

        # Buscar en respuestas
        answers = conversation.questionnaire_state.answers
        if "objetivo_principal" in answers and not objectives:
            objectives.append(answers["objetivo_principal"])

        if "objetivo_reuso" in answers:
            reuse_obj = answers["objetivo_reuso"]
            if isinstance(reuse_obj, list) and reuse_obj not in objectives:
                objectives.extend(reuse_obj)
            elif reuse_obj not in objectives:
                objectives.append(reuse_obj)

        # Si no hay objetivos específicos, usar algunos genéricos según el sector
        if not objectives and conversation.questionnaire_state.sector:
            if conversation.questionnaire_state.sector == "Industrial":
                objectives = [
                    "Cumplimiento normativo",
                    "Reducción de costos operativos",
                    "Reutilización de agua en procesos industriales",
                ]
            elif conversation.questionnaire_state.sector == "Comercial":
                objectives = [
                    "Sostenibilidad ambiental",
                    "Ahorro en costos de agua",
                    "Reutilización en sanitarios y riego",
                ]
            else:
                objectives = [
                    "Tratamiento eficiente de aguas residuales",
                    "Cumplimiento de normas ambientales",
                    "Optimización de recursos hídricos",
                ]

        return objectives

    def _extract_technical_parameters(
        self, conversation: Conversation
    ) -> Dict[str, Any]:
        """Extrae parámetros técnicos del agua"""
        params = {
            "dqo": None,
            "dbo": None,
            "sst": None,
            "ph": None,
            "grasas_aceites": None,
            "conductividad": None,
        }

        # Buscar en respuestas directas
        answers = conversation.questionnaire_state.answers
        if "parametros_agua" in answers and isinstance(
            answers["parametros_agua"], dict
        ):
            params_data = answers["parametros_agua"]
            for param in params.keys():
                if param in params_data:
                    params[param] = params_data[param]

        # Buscar en mensajes como fallback
        for msg in conversation.messages:
            if msg.role == "user":
                # Buscar DQO
                if not params["dqo"]:
                    dqo_match = re.search(
                        r"(?:DQO|COD).*?(\d+[\.,]?\d*)", msg.content, re.IGNORECASE
                    )
                    if dqo_match:
                        params["dqo"] = dqo_match.group(1)

                # Buscar DBO
                if not params["dbo"]:
                    dbo_match = re.search(
                        r"(?:DBO|BOD).*?(\d+[\.,]?\d*)", msg.content, re.IGNORECASE
                    )
                    if dbo_match:
                        params["dbo"] = dbo_match.group(1)

                # Buscar SST
                if not params["sst"]:
                    sst_match = re.search(
                        r"(?:SST|TSS).*?(\d+[\.,]?\d*)", msg.content, re.IGNORECASE
                    )
                    if sst_match:
                        params["sst"] = sst_match.group(1)

                # Buscar pH
                if not params["ph"]:
                    ph_match = re.search(
                        r"(?:pH).*?(\d+[\.,]?\d*)", msg.content, re.IGNORECASE
                    )
                    if ph_match:
                        params["ph"] = ph_match.group(1)

        return params

    def _format_objectives(self, objectives: List[str]) -> str:
        """Formatea los objetivos como lista con viñetas"""
        if not objectives:
            return "- Optimización del uso de agua\n- Cumplimiento normativo\n- Reducción de costos operativos"

        return "\n".join([f"- {obj}" for obj in objectives])

    def _summarize_provided_information(self, conversation: Conversation) -> str:
        """Genera un resumen de la información proporcionada por el usuario"""
        context = conversation.questionnaire_state.get_context_summary()

        # Formatearlo como tabla
        lines = context.split("\n")
        formatted_lines = []

        for line in lines:
            if ":" in line:
                parts = line.split(":", 1)
                formatted_lines.append(
                    f"| **{parts[0].strip()}** | {parts[1].strip()} |"
                )

        if formatted_lines:
            table = "| **Parámetro** | **Valor Proporcionado** |\n|--------------|------------------------|\n"
            table += "\n".join(formatted_lines)
            return table

        return context

    def _get_default_template(self) -> Dict[str, Any]:
        """Obtiene una plantilla de formato predeterminada"""
        return {
            "sections": [
                {
                    "title": "Información del Cliente",
                    "type": "table",
                    "fields": ["Cliente", "Ubicación", "Industria", "Fuente de Agua"],
                },
                {
                    "title": "Objetivos del Proyecto",
                    "type": "checklist",
                    "items": [
                        "Cumplimiento Normativo",
                        "Optimización de Costos",
                        "Reutilización de Agua",
                        "Sostenibilidad",
                    ],
                },
                # Más secciones según sea necesario
            ]
        }


# Instancia global
proposal_generator = ProposalGenerator()
