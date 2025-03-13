import json
import logging
import os
import random
from typing import Dict, Any, Optional, List, Tuple

from app.models.conversation import Conversation, QuestionnaireState
from app.config import settings

logger = logging.getLogger("hydrous-backend")


class QuestionnaireService:
    """Servicio para manejar el cuestionario y sus respuestas"""

    def __init__(self):
        self.questionnaire_data = self._load_questionnaire_data()

    def _load_questionnaire_data(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario desde un archivo JSON"""
        try:
            # En producción esto se cargaría desde un archivo
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
                        "text": "Nombre usuario/cliente/nombre de la empresa",
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
        return intro.get("text", ""), intro.get("explanation", "")

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
                "text": f"¿Cuál es el giro específico de tu Empresa dentro del sector {state.sector}?",
                "type": "multiple_choice",
                "options": self.get_subsectors(state.sector),
                "required": True,
                "explanation": "Cada subsector tiene características específicas que influyen en el diseño de la solución.",
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
                fact = self.get_random_fact(state.sector, state.subsector)

                # Añadir un hecho relevante a la explicación si existe
                if fact and q.get("explanation"):
                    q["explanation"] = (
                        f"{q['explanation']}\n\n*Dato interesante: {fact}*"
                    )

                return q

        # Si llegamos aquí, es que todas las preguntas han sido respondidas
        return None

    def process_answer(
        self, conversation: Conversation, question_id: str, answer: Any
    ) -> None:
        """Procesa una respuesta y actualiza el estado del cuestionario de manera más inteligente"""
        # Guardar la respuesta
        conversation.questionnaire_state.answers[question_id] = answer

        # Procesar respuestas a las preguntas especiales (sector y subsector)
        if question_id == "sector_selection":
            # Intentar determinar el sector a partir de la respuesta
            sectors = self.get_sectors()

            if isinstance(answer, str):
                # Si es un número, usarlo como índice
                if answer.isdigit():
                    sector_index = int(answer) - 1
                    if 0 <= sector_index < len(sectors):
                        conversation.questionnaire_state.sector = sectors[sector_index]
                # Si no es un número, buscar coincidencia por texto
                else:
                    answer_lower = answer.lower()
                    for sector in sectors:
                        if (
                            sector.lower() in answer_lower
                            or answer_lower in sector.lower()
                        ):
                            conversation.questionnaire_state.sector = sector
                            break

            # Si no se pudo determinar el sector, usar el primero como fallback
            if not conversation.questionnaire_state.sector and sectors:
                conversation.questionnaire_state.sector = sectors[0]

        elif question_id == "subsector_selection":
            if conversation.questionnaire_state.sector:
                subsectors = self.get_subsectors(
                    conversation.questionnaire_state.sector
                )

                if isinstance(answer, str):
                    # Si es un número, usarlo como índice
                    if answer.isdigit():
                        subsector_index = int(answer) - 1
                        if 0 <= subsector_index < len(subsectors):
                            conversation.questionnaire_state.subsector = subsectors[
                                subsector_index
                            ]
                    # Si no es un número, buscar coincidencia por texto
                    else:
                        answer_lower = answer.lower()
                        for subsector in subsectors:
                            if (
                                subsector.lower() in answer_lower
                                or answer_lower in subsector.lower()
                            ):
                                conversation.questionnaire_state.subsector = subsector
                                break

                # Si no se pudo determinar el subsector, usar el primero como fallback
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
            if obj_principal.isdigit():
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
                    if r.isdigit():
                        r_index = int(r) - 1
                        options = self._get_options_for_question(
                            "objetivo_reuso", sector, subsector
                        )
                        if 0 <= r_index < len(options):
                            reuse_objectives.append(options[r_index])
                    else:
                        reuse_objectives.append(r)
            elif reuse.isdigit():
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
        """Formatea un resumen de la propuesta para presentar al usuario de manera más atractiva"""
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

        # Crear una introducción personalizada
        intro = f"¡Excelente, {client_info['name']}! Gracias por completar el cuestionario. Basado en tus respuestas, he preparado una propuesta personalizada para tu proyecto de tratamiento de aguas residuales en el sector {client_info['sector']} - {client_info['subsector']}."

        # Formatear objetivos principales
        objetivos_principales = (
            "• " + "\n• ".join(project_details["objectives"])
            if project_details.get("objectives")
            else "No especificados"
        )

        # Formatear objetivos de reúso
        objetivos_reuso = (
            "• " + "\n• ".join(project_details["reuse_objectives"])
            if project_details.get("reuse_objectives")
            else "No especificados"
        )

        # Formatear resumen con más detalle y mejor presentación
        summary = f"""
{intro}

**RESUMEN DE LA PROPUESTA DE HYDROUS**

**📋 DATOS DEL PROYECTO**
• Cliente: {client_info['name']}
• Ubicación: {client_info['location']}
• Sector: {client_info['sector']} - {client_info['subsector']}
• Flujo de agua a tratar: {project_details.get('flow_rate', 'No especificado')}

**🎯 OBJETIVOS PRINCIPALES**
{objetivos_principales}

**♻️ OBJETIVOS DE REÚSO**
{objetivos_reuso}

**⚙️ SOLUCIÓN TECNOLÓGICA RECOMENDADA**
• **Pretratamiento**: {", ".join(treatment['pretratamiento']['tecnologias']) if 'pretratamiento' in treatment and treatment['pretratamiento'] and 'tecnologias' in treatment['pretratamiento'] else "No requerido"}
• **Tratamiento primario**: {", ".join(treatment['primario']['tecnologias']) if 'primario' in treatment and treatment['primario'] and 'tecnologias' in treatment['primario'] else "No requerido"}
• **Tratamiento secundario**: {", ".join(treatment['secundario']['tecnologias']) if 'secundario' in treatment and treatment['secundario'] and 'tecnologias' in treatment['secundario'] else "No requerido"}
• **Tratamiento terciario**: {", ".join(treatment['terciario']['tecnologias']) if 'terciario' in treatment and treatment['terciario'] and 'tecnologias' in treatment['terciario'] else "No requerido"}

**💰 ANÁLISIS ECONÓMICO**
• Inversión inicial estimada: ${costs['capex']['total']:,.2f} USD
• Costo operativo anual: ${costs['opex']['total_anual']:,.2f} USD/año
• Costo operativo mensual: ${costs['opex']['total_mensual']:,.2f} USD/mes

**📈 RETORNO DE INVERSIÓN**
• Ahorro anual estimado: ${roi['ahorro_anual']:,.2f} USD/año
• Periodo de recuperación: {roi['periodo_recuperacion']:.1f} años
• ROI a 5 años: {roi['roi_5_anos']:.1f}%

**🌱 BENEFICIOS AMBIENTALES**
• Reducción de la huella hídrica de tu operación
• Disminución de la descarga de contaminantes al medio ambiente
• Cumplimiento con normativas ambientales vigentes
• Contribución a la sostenibilidad del recurso hídrico

**PRÓXIMOS PASOS**
¿Te gustaría recibir una propuesta detallada por correo electrónico? ¿O prefieres programar una reunión con nuestros especialistas para revisar en detalle esta recomendación y resolver cualquier duda específica?

También puedo responder cualquier pregunta adicional que tengas sobre la solución propuesta.
"""
        return summary

    def get_questionnaire_as_context(
        self, sector: str = None, subsector: str = None
    ) -> str:
        """
        Obtiene el cuestionario completo como contexto para el modelo de IA,
        opcionalmente filtrado por sector y subsector.

        Args:
            sector: Sector específico (ej. "Industrial")
            subsector: Subsector específico (ej. "Textil")

        Returns:
            str: Texto del cuestionario relevante
        """
        # Texto completo del cuestionario (preámbulo)
        context = """
        **\"¡Hola! Gracias por tomarte el tiempo para responder estas preguntas.
        La información que nos compartas nos ayudará a diseñar una solución de
        agua personalizada, eficiente y rentable para tu operación. No te
        preocupes si no tienes todas las respuestas a la mano; iremos paso a
        paso y te explicaré por qué cada pregunta es importante. ¡Empecemos!\"**

        **Antes de entrar en detalles técnicos, me gustaría conocer un poco más
        sobre tu empresa y el sector en el que opera. Esto nos ayudará a
        entender mejor tus necesidades y diseñar una solución de agua adecuada
        para ti. Vamos con las primeras preguntas.\"**
        """

        # Si no se especifica sector, devolvemos solo la lista de sectores
        if not sector:
            context += """
            ¿En qué sector opera tu empresa?

            - Industrial
            - Comercial
            - Municipal
            - Residencial
            """
            return context

        # Si se especifica sector pero no subsector, devolvemos la lista de subsectores
        if sector and not subsector:
            if sector == "Industrial":
                context += """
                ¿Cuál es el giro especifico de tu Empresa dentro este Sector?

                **Industrial**
                - Alimentos y Bebidas
                - Textil
                - Petroquímica
                - Farmacéutica
                - Minería
                - Petróleo y Gas
                - Metal/Automotriz
                - Cemento
                - Otro
                """
            elif sector == "Comercial":
                context += """
                ¿Cuál es el giro especifico de tu Empresa dentro este Sector?

                **Comercial**
                - Hotel
                - Edificio de oficinas
                - Centro comercial/Comercio minorista
                - Restaurante
                """
            elif sector == "Municipal":
                context += """
                ¿Cuál es el giro especifico de tu Empresa dentro este Sector?

                **Municipal**
                - Gobierno de la ciudad
                - Pueblo/Aldea
                - Autoridad de servicios de agua
                """
            elif sector == "Residencial":
                context += """
                ¿Cuál es el giro especifico de tu Empresa dentro este Sector?

                **Residencial**
                - Vivienda unifamiliar
                - Edificio multifamiliar
                """
            return context

        # Si tenemos sector y subsector, devolvemos el cuestionario específico
        # Aquí incluiríamos el texto completo del cuestionario para esa combinación
        context += f"\n**Sector: {sector}**\n**Subsector: {subsector}**\n\n"

        # Ejemplo para Industrial_Textil (se implementaría para todas las combinaciones)
        if sector == "Industrial" and subsector == "Textil":
            context += """
            **"Para continuar, quiero conocer algunos datos clave sobre tu empresa,
            como la ubicación y el costo del agua. Estos factores pueden influir en
            la viabilidad de distintas soluciones. Por ejemplo, en ciertas regiones,
            el agua puede ser más costosa o escasa, lo que hace que una solución de
            tratamiento o reutilización sea aún más valiosa. ¡Vamos con las
            siguientes preguntas!\"**

            1. Nombre usuario/cliente/nombre de la empresa
            2. Ubicación (Colonia, Ciudad, código Postal, coordenadas)
            3. Costo del agua (moneda/unidad de medición)
            4. Cantidad de agua consumida (Unidad de medición/unidad tiempo)
            5. Cantidad de aguas residuales generadas (unidad de medición/unidad de tiempo)
            6. Aproximadamente cuantas personas (empleados, clientes, visitantes) atiende tus instalaciones por día o por semana
               - Menos de 20
               - >=20, <50
               - >50, < 200
               - >= 200, < 500
               - >=500<1000
               - >=1000<2000
               - >=2000<5000
               - >=5000

            7. Volúmenes de agua promedios, picos de generación de agua residual
            8. Análisis de agua residual (de preferencia históricos):
               - Color
               - SST (Solidos suspendidos)
               - pH (Potencial Hidrogeno)
               - Metales pesados (Mercurio, arsénico, plomo etc.)
               - DQO (Demanda química de oxígeno)
               - DBO (Demanda bioquímica de oxígeno)
               
            9. Cuál es su fuente de agua
               - Agua municipal
               - Agua de pozo
               - Cosecha de agua Pluvial
               
            10. Cuales son sus usos en su empresa:
                - Lavado de telas
                - Teñido e impresión
                - Enjuague y acabado
                - Agua de refrigeración
                - Agua para Calderas (generación de vapor)
                
            11. Volúmenes de agua potable promedios, picos de consumo
            
            12. Cual es el objetivo principal que estas buscando
                - Cumplimiento normativo
                - Reducción de la huella ambiental
                - Ahorro de costos/Proyecto de retorno de inversión
                - Mayor disponibilidad de agua
                - Otro (especifique)
                
            13. Objetivos de reusó del agua o descarga del agua tratada:
                - Uso en riego de áreas verdes
                - Rehusó en sanitarios
                - Rehusó en sus procesos industriales
                - Cumplimiento normativo
                - Otro Especifique
                
            14. ¿Actualmente en donde descarga sus aguas residuales?
                - Alcantarillado
                - Cuerpo de agua natural (Ríos, Lagunas Esteros o Subsuelo)
                - Otro (Especifique)
                
            15. Cuenta con algunas restricciones adicionales del proyecto:
                - Limitaciones de espacio y logística
                - Restricciones normativas o regulatorias
                - Calidad del agua en la entrada
                - Limitaciones en las tecnologías disponibles
                - Rangos de presupuestos descríbalos por favor
                - Inversión inicial limitada
                - Preocupación por costos operativos
                - Manejo de residuos
                - Disponibilidad de energía local
                - Otros (especifique)
                
            16. Cuenta con algún sistema de tratamiento de agua residual o sistema de potabilización
                - Si
                - No
                
            17. Que presupuesto tiene estimado para la inversión en proyectos de agua
            18. En que tiempo tiene contemplado llevar a cabo el proyecto
            19. Cuenta con financiamiento disponible
            20. Puede proporcionarnos recibos del agua
            21. Cuenta con un cronograma estimado para la implementación de los proyectos
            22. Tiempo contemplado en el crecimiento de proyectos a futuro
                - Inmediato (0-6 meses)
                - Corto plazo (6-12 meses)
                - Mediano plazo (1-3 años)
                - Otro especifique
            """
        # Se agregarían condiciones similares para todas las combinaciones de sector_subsector

        return context

    def get_proposal_format(self) -> str:
        """
        Obtiene el formato de propuesta para usar como plantilla

        Returns:
            str: Texto del formato de propuesta
        """
        return """
        **Hydrous Management Group -- AI-Generated Wastewater Treatment Proposal
        Guideline**

        **📌 Important Disclaimer**

        This proposal was **generated using AI** based on the information
        provided by the end user and **industry-standard benchmarks**. While
        every effort has been made to ensure accuracy, the data, cost estimates,
        and technical recommendations **may contain errors and are not legally
        binding**. It is recommended that all details be **validated by Hydrous
        Management Group** before implementation.

        If a **phone number or contact information** was provided, a
        representative from **Hydrous Management Group will reach out** for
        further discussion. If not, you may contact us at **info@hydrous.com**
        for additional inquiries or clarification.

        **1. Introduction to Hydrous Management Group**

        Hydrous Management Group specializes in **customized wastewater
        treatment solutions** tailored for industrial and commercial clients.
        Our **expertise in water management** helps businesses achieve
        **regulatory compliance, cost reductions, and sustainable water reuse**.

        Using advanced treatment technologies and AI-powered design, Hydrous
        delivers **efficient, scalable, and cost-effective** wastewater
        solutions that optimize operational performance while minimizing
        environmental impact.

        **2. Project Background**

        This section provides an overview of the client's facility, industry,
        and wastewater treatment needs.

        **3. Objective of the Project**

        Clearly define the **primary objectives** for wastewater treatment.

        ✅ **Regulatory Compliance** -- Ensure treated wastewater meets
        discharge regulations.
        ✅ **Cost Optimization** -- Reduce water purchase and discharge costs.
        ✅ **Water Reuse** -- Treat wastewater for use in industrial processes.
        ✅ **Sustainability** -- Improve environmental footprint through
        efficient resource management.

        **4. Key Design Assumptions & Comparison to Industry Standards**

        This section compares the **raw wastewater characteristics** provided by
        the client with **industry-standard values** for similar industrial
        wastewater. It also outlines the target effluent quality for compliance
        or reuse.

        **5. Process Design & Treatment Alternatives**

        This section outlines **recommended treatment technologies** and
        possible **alternatives** to meet wastewater treatment objectives.

        **6. Suggested Equipment & Sizing**

        This section lists **recommended equipment, capacities, dimensions, and
        possible vendors/models** where available.

        **7. Estimated CAPEX & OPEX**

        This section itemizes both **capital expenditure (CAPEX)** and
        **operational expenditure (OPEX)**.

        **8. Return on Investment (ROI) Analysis**

        Projected cost savings based on **reduced water purchases and lower
        discharge fees**.

        **9. Q&A Exhibit**

        Attach all **key questions and answers** gathered during consultation as
        an exhibit for reference.

        📩 **For inquiries or validation of this proposal, contact Hydrous
        Management Group at:** **info@hydrous.com**.
        """


# Instancia global del servicio
questionnaire_service = QuestionnaireService()
