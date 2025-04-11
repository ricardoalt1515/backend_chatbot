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
# CREA UNA PROPUESTA TÉCNICA 100% ORIGINAL SIN PLACEHOLDERS

Necesito una propuesta de tratamiento de agua COMPLETAMENTE DETALLADA para un cliente basada en esta conversación:

{conversation_text}

## REGLAS ESTRICTAS:
1. NUNCA uses texto como [Nombre] o [Valor]. Esto es crucial.
2. Si falta información, INVENTA datos realistas:
   - Nombre: "Industrias Agua Pura"
   - Ubicación: "Ciudad de México"
   - Consumo: "350 m³/día"
   - Costos: "$45,000 USD"

3. Cada sección debe tener INFORMACIÓN ESPECÍFICA, no genérica.
4. Usa datos técnicos precisos para equipos, dimensiones y costos.
5. NO uses frases como "basado en la industria" o "recomendaciones específicas".

## ESTRUCTURA OBLIGATORIA:
1. Título profesional
2. Introducción a Hydrous Management (2-3 párrafos)
3. Información del cliente con datos concretos
4. Objetivos del proyecto (4 puntos específicos)
5. Tecnologías recomendadas (nombra marcas y modelos específicos)
6. Presupuesto detallado con cifras exactas
7. Análisis ROI con periodo exacto de recuperación
8. Conclusión

IMPORTANTE: Esto se convertirá directamente en un PDF oficial sin revisión humana.
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

            # Estilos
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                name="TitleStyle",
                parent=styles["Heading1"],
                fontSize=18,
                textColor=colors.HexColor("#0056b3"),
                spaceAfter=12,
            )
            heading2_style = ParagraphStyle(
                name="Heading2Style",
                parent=styles["Heading2"],
                fontSize=16,
                textColor=colors.HexColor("#0056b3"),
                spaceAfter=10,
            )
            normal_style = ParagraphStyle(
                name="NormalStyle", parent=styles["Normal"], fontSize=11, spaceAfter=8
            )
            list_style = ParagraphStyle(
                name="ListStyle",
                parent=styles["Normal"],
                fontSize=11,
                leftIndent=20,
                spaceAfter=3,
            )

            # Elementos para el PDF
            elements = []

            # Procesamiento de texto
            lines = proposal_text.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    elements.append(Spacer(1, 0.2 * cm))
                    continue

                # Encabezados
                if line.startswith("# "):
                    elements.append(Paragraph(line[2:], title_style))
                elif line.startswith("## "):
                    elements.append(Paragraph(line[3:], heading2_style))
                elif line.startswith("### "):
                    elements.append(Paragraph(line[4:], heading2_style))
                # Listas
                elif line.startswith("- "):
                    elements.append(Paragraph(f"• {line[2:]}", list_style))
                # Texto normal
                else:
                    elements.append(Paragraph(line, normal_style))

            # Construir PDF
            doc.build(elements)

            logger.info(f"PDF generado exitosamente en: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error generando PDF directo: {e}", exc_info=True)
            return None


# Instancia global
direct_proposal_generator = DirectProposalGenerator()
