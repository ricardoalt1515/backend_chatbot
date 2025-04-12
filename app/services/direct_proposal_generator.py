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
# CREA UNA PROPUESTA PROFESIONAL DE TRATAMIENTO DE AGUA SIGUIENDO EL FORMATO ESPECÍFICO

Basándote en la siguiente conversación con el cliente:

{conversation_text}

## INSTRUCCIONES IMPORTANTES:
1. Crea una propuesta DETALLADA y PROFESIONAL siguiendo EXACTAMENTE la estructura indicada a continuación.
2. Usa DATOS ESPECÍFICOS del cliente - NUNCA uses placeholders. Si falta información, INVENTA datos realistas.
3. Para cada sección, incluye información TÉCNICAMENTE PRECISA y COMPLETA.
4. Usa un lenguaje profesional, técnico y persuasivo propio de ingeniería ambiental.

## ESTRUCTURA OBLIGATORIA (respeta fielmente todos los títulos y secciones):

1. **Hydrous Management Group – AI-Generated Wastewater Treatment Proposal**
   - Incluye un disclaimer profesional sobre la generación con IA.

2. **Introduction to Hydrous Management Group**
   - Describe la especialización en soluciones de tratamiento de aguas residuales.
   - Menciona la experiencia en gestión del agua, cumplimiento normativo, etc.
   - Resalta el uso de tecnologías avanzadas y diseño asistido por IA.

3. **Project Background**
   - Crea una tabla con "Client Information" que incluya:
     - Client Name (específico, sin placeholders)
     - Location (específico, sin placeholders)
     - Industry (basado en la conversación)
     - Water Source, Consumption, Wastewater Generation
     - Existing Treatment System (si existe o "No existing treatment")

4. **Objective of the Project**
   - Lista con viñetas (✅) para cada objetivo:
     - Regulatory Compliance
     - Cost Optimization
     - Water Reuse
     - Sustainability
   - Incluye una descripción específica para cada objetivo.

5. **Key Design Assumptions & Comparison to Industry Standards**
   - Crea una tabla comparativa con parámetros como TSS, TDS, COD, BOD, pH.
   - Incluye columnas para valores actuales, estándares de la industria, y objetivos.
   - Usa valores numéricos específicos basados en el sector industrial.

6. **Process Design & Treatment Alternatives**
   - Crea una tabla detallando cada etapa de tratamiento:
     - Primary Treatment (e.g., DAF)
     - pH Adjustment
     - Secondary Treatment (e.g., MBBR)
     - Tertiary Treatment
     - Disinfection
     - Water Reuse System (if applicable)
   - Para cada tecnología, incluye una descripción técnica y una alternativa.

7. **Suggested Equipment & Sizing**
   - Tabla detallada con:
     - Equipos específicos (nombres y modelos)
     - Capacidades (valores numéricos específicos)
     - Dimensiones (valores concretos)
     - Marcas/modelos recomendados

8. **Estimated CAPEX & OPEX**
   - Desglose detallado de CAPEX por categoría (valores específicos en USD)
   - Desglose mensual de OPEX (químicos, energía, mano de obra, disposición de lodos)
   - Incluye notas y justificaciones para cada costo.

9. **Return on Investment (ROI) Analysis**
   - Tabla comparativa de costos actuales vs. proyectados
   - Cálculo específico del ROI en años
   - Justificación de los ahorros y beneficios

10. **Q&A Exhibit**
    - Resumen de las preguntas más importantes de la consulta
    - Incluye datos de contacto de Hydrous Management Group

Asegúrate de que el contenido sea técnicamente sólido, específico al cliente, y con valores realistas para el sector industrial correspondiente.
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

        table = Table(data, repeatRows=1)
        table_style = TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0056b3")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
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
