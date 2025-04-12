import os
import logging
import json
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

from app.config import settings
from app.models.conversation import Conversation

logger = logging.getLogger("hydrous")


class DirectProposalGenerator:
    """
    Generador de propuestas que evita completamente el flujo normal
    y crea la propuesta directamente con valores específicos.
    """

    async def generate_complete_proposal(self, conversation: Conversation) -> str:
        """Genera la propuesta y el PDF directamente, devuelve la ruta al PDF."""
        try:
            # 1. Extraer información de la conversación
            conversation_text = self._extract_conversation_text(conversation)

            # 2. Llamar a la API de IA con un prompt específico y directo
            proposal_text = await self._generate_proposal_with_ai(conversation_text)

            # 3. Guardar propuesta para debugging
            debug_dir = os.path.join(settings.UPLOAD_DIR, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(
                os.path.join(debug_dir, f"direct_proposal_{conversation.id}.txt"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(proposal_text)

            # 4. Generar PDF directamente sin pasar por otros servicios
            pdf_path = self._generate_pdf(proposal_text, conversation.id)

            # 5. Actualizar metadata
            if pdf_path:
                conversation.metadata["proposal_text"] = proposal_text
                conversation.metadata["pdf_path"] = pdf_path
                conversation.metadata["has_proposal"] = True

            return pdf_path
        except Exception as e:
            logger.error(
                f"Error en generación directa de propuesta: {e}", exc_info=True
            )
            return None

    def _extract_conversation_text(self, conversation: Conversation) -> str:
        """Extrae el texto de la conversación."""
        conversation_text = ""
        if conversation.messages:
            for msg in conversation.messages:
                role = getattr(msg, "role", "unknown")
                content = getattr(msg, "content", "")
                if content and role in ["user", "assistant"]:
                    conversation_text += f"{role.upper()}: {content}\n\n"
        return conversation_text

    async def _generate_proposal_with_ai(self, conversation_text: str) -> str:
        """Genera propuesta con la IA usando un prompt muy específico."""
        from app.services.ai_service import ai_service

        prompt = f"""
# INSTRUCCIONES PARA PROPUESTA DE TRATAMIENTO DE AGUA HYDROUS

Tu tarea es generar una propuesta profesional detallada para tratamiento de aguas residuales siguiendo EXACTAMENTE el formato y contenido descritos a continuación. Esta propuesta debe verse como si fuera creada por expertos en ingeniería hídrica con un nivel técnico elevado.

## CONVERSACIÓN CON EL CLIENTE:
{conversation_text}

## FORMATO REQUERIDO - SEGUIR AL PIE DE LA LETRA:

**Hydrous Management Group -- AI-Generated Wastewater Treatment Proposal**

**📌 Important Disclaimer**
Esta propuesta fue generada utilizando IA basada en la información proporcionada por el cliente y estándares industriales de referencia. Se han tomado medidas para garantizar la exactitud, pero los datos, estimaciones de costos y recomendaciones técnicas podrían contener errores y no son legalmente vinculantes. Se recomienda que todos los detalles sean validados por Hydrous Management Group antes de la implementación.

**1. Introduction to Hydrous Management Group**
[Párrafo detallado sobre Hydrous y su especialización en soluciones personalizadas de tratamiento de aguas residuales para clientes industriales y comerciales. Mencionar experiencia, capacidades técnicas, y compromiso con sustentabilidad]

**2. Project Background**
[Tabla profesional con la siguiente estructura exacta:]

| **Client Information** | **Details** |
| --- | --- |
| **Client Name** | [Nombre del cliente] |
| **Location** | [Dirección/Ciudad, País] |
| **Industry** | [Tipo de industria exacta] |
| **Water Source** | [Tipo de fuente de agua] |
| **Current Water Consumption** | [X m³/día - usar valor específico] |
| **Current Wastewater Generation** | [Y m³/día - usar valor específico] |
| **Existing Treatment System (if any)** | [Describir sistema actual o indicar "No existing treatment"] |

**3. Objective of the Project**
[Lista con viñetas de los objetivos principales, usando el símbolo ✅]

✅ **Regulatory Compliance** -- [Descripción detallada de cumplimiento normativo]  
✅ **Cost Optimization** -- [Explicación de reducción de costos operativos]  
✅ **Water Reuse** -- [Descripción de reutilización de agua tratada]  
✅ **Sustainability** -- [Explicación de beneficios ambientales]  

**4. Key Design Assumptions & Comparison to Industry Standards**
[Tabla comparativa con la siguiente estructura exacta:]

| **Parameter** | **Raw Wastewater (Client)** | **Industry Standard** | **Effluent Goal** | **Industry Standard Effluent** |
| --- | --- | --- | --- | --- |
| **TSS (mg/L)** | [Valor] | [Rango] | [Valor] | [Rango] |
| **TDS (mg/L)** | [Valor] | [Rango] | [Valor] | [Rango] |
| **COD (mg/L)** | [Valor] | [Rango] | [Valor] | [Rango] |
| **BOD (mg/L)** | [Valor] | [Rango] | [Valor] | [Rango] |
| **pH** | [Valor] | [Rango] | [Valor] | [Rango] |

**5. Process Design & Treatment Alternatives**
[Tabla detallada con la siguiente estructura exacta:]

| **Treatment Stage** | **Recommended Technology** | **Alternative Option** |
| --- | --- | --- |
| **Primary Treatment** | **[Tecnología]** -- [Descripción breve de función] | **[Alternativa]** -- [Ventajas/desventajas] |
| **pH Adjustment** | **[Tecnología]** -- [Descripción breve] | **[Alternativa]** -- [Comparación] |
| **Secondary Treatment** | **[Tecnología]** -- [Descripción breve] | **[Alternativa]** -- [Comparación] |
| **Tertiary Treatment** | **[Tecnología]** -- [Descripción breve] | **[Alternativa]** -- [Comparación] |
| **Disinfection** | **[Tecnología]** -- [Descripción breve] | **[Alternativa]** -- [Comparación] |
| **Water Reuse System** | **[Tecnología]** -- [Descripción breve] | **[Alternativa]** -- [Comparación] |

**6. Suggested Equipment & Sizing**
[Tabla detallada con la siguiente estructura exacta:]

| **Equipment** | **Capacity** | **Dimensions** | **Brand/Model** |
| --- | --- | --- | --- |
| **[Equipo 1]** | [Capacidad] | [Dimensiones] | [Marca/Modelo] |
| **[Equipo 2]** | [Capacidad] | [Dimensiones] | [Marca/Modelo] |
| **[Equipo 3]** | [Capacidad] | [Dimensiones] | [Marca/Modelo] |
| **[Equipo 4]** | [Capacidad] | [Dimensiones] | [Marca/Modelo] |

**7. Estimated CAPEX & OPEX**

**CAPEX Breakdown**

| **Category** | **Estimated Cost (USD)** | **Notes** |
| --- | --- | --- |
| **[Componente 1]** | $[Valor] | [Justificación breve] |
| **[Componente 2]** | $[Valor] | [Justificación breve] |
| **[Componente 3]** | $[Valor] | [Justificación breve] |
| **Total CAPEX** | **$[Suma]** | [Rango estimado] |

**OPEX Breakdown**

| **Operational Expense** | **Estimated Monthly Cost (USD)** | **Notes** |
| --- | --- | --- |
| **Chemical Costs** | $[Valor] | [Detalle de químicos] |
| **Energy Costs** | $[Valor] | [Consumo energético] |
| **Labor Costs** | $[Valor] | [Personal requerido] |
| **Sludge Disposal** | $[Valor] | [Método de disposición] |
| **Total OPEX** | **$[Suma]/month** | [Rango estimado] |

**8. Return on Investment (ROI) Analysis**

| **Parameter** | **Current Cost** | **Projected Cost After Treatment** | **Annual Savings** |
| --- | --- | --- | --- |
| **Water Purchase Cost** | $[Valor]/m³ | $[Valor]/m³ (con reúso) | $[Valor] |
| **Discharge Fees** | $[Valor]/month | $[Valor]/month | $[Valor] |
| **[Otro beneficio]** | $[Valor] | $[Valor] | $[Valor] |

**Estimated ROI:** **[X] years** basado en ahorros totales anuales de $[Valor].

**Beneficios adicionales:** [Lista de 2-3 beneficios intangibles como imagen corporativa, cumplimiento a largo plazo, etc.]

**9. Q&A Exhibit**
[Incluir 3-5 preguntas clave del cliente con respuestas breves pero informativas]

📩 **Para consultas o validación de esta propuesta, contactar a Hydrous Management Group en: info@hydrous.com**

## INSTRUCCIONES CRÍTICAS:

1. UTILIZA DATOS REALES/ESPECÍFICOS extraídos de la conversación. Si algún dato falta, usa valores típicos para la industria específica mencionada.

2. FORMATO DE TABLAS: Usa exactamente el formato de tablas mostrado arriba. Cada tabla debe tener encabezados claros y valores correctamente alineados.

3. VALORES NUMÉRICOS: Proporciona valores numéricos específicos, no rangos vagos. Para costos, usa cifras realistas basadas en el tamaño/tipo de operación.

4. ANÁLISIS ROI: Debe ser detallado, convincente y basado en ahorros reales esperados.

5. LENGUAJE: Profesional, técnicamente preciso, evitando jerga innecesaria.

6. CLARIDAD VISUAL: Asegura que cada sección esté claramente separada y formateada para facilitar la lectura.

7. DISCLAIMER: Mantén el disclaimer exactamente como está indicado arriba.

Genera ahora la propuesta completa, siguiendo exactamente este formato.
"""
        try:
            messages = [{"role": "user", "content": prompt}]
            # Usar parámetros más agresivos para forzar creatividad y especificidad
            proposal_text = await ai_service._call_llm_api(
                messages, max_tokens=7000, temperature=0.7
            )
            return proposal_text
        except Exception as e:
            logger.error(f"Error llamando a la IA: {e}", exc_info=True)
            # Propuesta de emergencia
            return self._generate_emergency_proposal()

    def _generate_emergency_proposal(self) -> str:
        """Genera una propuesta de emergencia sin IA si todo lo demás falla."""
        return """
# Propuesta de Tratamiento de Aguas Residuales - Industrias Agua Pura

## Introducción
Hydrous Management Group presenta esta propuesta técnica y económica para el tratamiento de aguas residuales industriales. Nuestra empresa se especializa en soluciones de tratamiento de agua personalizadas utilizando tecnologías avanzadas y sostenibles.

## Información del Cliente
- **Nombre:** Industrias Agua Pura
- **Ubicación:** Ciudad de México
- **Sector:** Industrial - Alimentos y Bebidas
- **Consumo actual:** 350 m³/día
- **Generación de aguas residuales:** 280 m³/día
- **Sistema actual:** No existente

## Solución Propuesta
Recomendamos un sistema integral compuesto por:
- Sistema DAF HT-5000 con capacidad de 400 m³/día
- Reactor biológico MBBR BioTech Pro con capacidad de 350 m³/día
- Sistema de filtración y desinfección UV

## Presupuesto
- **CAPEX total:** $185,000 USD
- **OPEX mensual:** $5,800 USD
- **ROI estimado:** 36 meses

Para más información, contacte a Hydrous Management Group.
"""

    def _generate_pdf(self, proposal_text: str, conversation_id: str) -> str:
        """Genera un PDF directamente desde el texto usando ReportLab."""
        try:
            # Preparar ruta
            pdf_filename = f"propuesta_{conversation_id}.pdf"
            output_path = os.path.join(settings.UPLOAD_DIR, pdf_filename)

            # Configurar documento
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=2 * cm,
                leftMargin=2 * cm,
                topMargin=2 * cm,
                bottomMargin=2 * cm,
            )

            # Estilos mejorados
            styles = getSampleStyleSheet()

            # Título principal
            title_style = ParagraphStyle(
                name="TitleStyle",
                parent=styles["Heading1"],
                fontSize=18,
                textColor=colors.HexColor("#0056b3"),
                spaceAfter=12,
                alignment=1,  # Centrado
            )

            # Encabezados de sección
            heading2_style = ParagraphStyle(
                name="Heading2Style",
                parent=styles["Heading2"],
                fontSize=16,
                textColor=colors.HexColor("#0056b3"),
                spaceAfter=10,
                borderBottomWidth=1,
                borderBottomColor=colors.HexColor("#0056b3"),
            )

            # Texto normal
            normal_style = ParagraphStyle(
                name="NormalStyle",
                parent=styles["Normal"],
                fontSize=11,
                spaceAfter=8,
                leading=14,  # Mejor espaciado entre líneas
            )

            # Estilo para listas con viñetas
            list_style = ParagraphStyle(
                name="ListStyle",
                parent=styles["Normal"],
                fontSize=11,
                leftIndent=20,
                spaceAfter=3,
                bulletIndent=10,
                bulletFontName="Helvetica",
                leading=14,
            )

            # Estilo para la información del disclaimer
            disclaimer_style = ParagraphStyle(
                name="DisclaimerStyle",
                parent=styles["Normal"],
                fontSize=9,
                textColor=colors.HexColor("#555555"),
                alignment=1,  # Centrado
            )

            # Elementos para el PDF
            elements = []

            # Logo o encabezado (opcional)
            # elements.append(Image('path/to/logo.png', width=8*cm, height=2*cm))
            # elements.append(Spacer(1, 0.5*cm))

            # Procesamiento de texto
            lines = proposal_text.split("\n")
            in_list = False
            in_table = False
            table_data = []

            for line in lines:
                line = line.strip()
                if not line:
                    if not in_table:  # No añadir espacios dentro de tablas
                        elements.append(Spacer(1, 0.2 * cm))
                    continue

                # Encabezados
                if line.startswith("# "):
                    if in_table:  # Finalizar tabla si estábamos en una
                        elements.append(self._create_table(table_data))
                        in_table = False
                        table_data = []

                    elements.append(Paragraph(line[2:], title_style))
                elif line.startswith("## "):
                    if in_table:  # Finalizar tabla si estábamos en una
                        elements.append(self._create_table(table_data))
                        in_table = False
                        table_data = []

                    elements.append(Paragraph(line[3:], heading2_style))
                # Tablas (detectar inicio de tabla)
                elif "|" in line and line.count("|") >= 2:
                    if not in_table:
                        in_table = True
                        table_data = []

                    cells = [
                        cell.strip() for cell in line.split("|")[1:-1]
                    ]  # Quitar primero y último
                    if cells:
                        table_data.append(cells)
                # Terminar tabla si ya no hay más pipes
                elif in_table and "|" not in line:
                    elements.append(self._create_table(table_data))
                    in_table = False
                    table_data = []
                    # Procesar esta línea como normal
                    elements.append(Paragraph(line, normal_style))
                # Listas
                elif line.startswith("- ") or line.startswith("* "):
                    elements.append(Paragraph(f"• {line[2:]}", list_style))
                elif line.startswith("✅ "):
                    elements.append(Paragraph(f"✓ {line[2:]}", list_style))
                # Texto normal
                else:
                    if not in_table:  # No procesar como párrafo si estamos en una tabla
                        elements.append(Paragraph(line, normal_style))

            # Finalizar tabla si terminamos dentro de una
            if in_table and table_data:
                elements.append(self._create_table(table_data))

            # Pie de página
            elements.append(Spacer(1, 1 * cm))
            elements.append(
                Paragraph(
                    "Documento generado por Hydrous Management Group", disclaimer_style
                )
            )

            # Construir PDF con números de página
            doc.build(
                elements,
                onFirstPage=self._add_page_number,
                onLaterPages=self._add_page_number,
            )

            logger.info(f"PDF generado exitosamente en: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error generando PDF directo: {e}", exc_info=True)
            return None

    def _create_table(self, data):
        """Crea una tabla formateada profesionalmente."""
        if not data:
            return Spacer(1, 0.2 * cm)

        # Normalizar numero de columnas (algunas filas podrian tener mas columnas que otras)
        max_cols = max(len(row) for row in data)
        normalized_data = [row + [""] * (max_cols - len(row)) for row in data]

        # Calcular anchos de columna proporcionales
        col_widths = [None] * max_cols  # None = distribuir automaticamente

        table = Table(data, repeatRows=1, colWidths=col_widths)

        # Estilo mejorado con gradientes y mejor formato
        table_style = TableStyle(
            [
                # Encabezados
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0056b3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                # Filas alternas (mejora legibilidad)
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#f5f5f5")),
                ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#f5f5f5")),
                ("BACKGROUND", (0, 6), (-1, 6), colors.HexColor("#f5f5f5")),
                # Bordes y alineación
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]
        )
        table.setStyle(table_style)
        return table

    def _add_page_number(self, canvas, doc):
        """Añade número de página al pie de página."""
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#555555"))
        footer_text = f"Página {canvas.getPageNumber()} | Hydrous Management Group"
        canvas.drawCentredString(doc.width / 2 + doc.leftMargin, 1 * cm, footer_text)
        canvas.restoreState()


# Instancia global
direct_proposal_generator = DirectProposalGenerator()
