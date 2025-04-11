# new_proposal_service.py


class NewProposalService:
    async def generate_simple_proposal(
        self, conversation_id: str, conversation_text: str
    ) -> str:
        """Genera una propuesta simple basada en el texto de la conversación."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
            from reportlab.lib.styles import getSampleStyleSheet

            # Texto de propuesta predeterminado con datos inventados
            proposal_text = """
            # Propuesta de Sistema de Tratamiento de Aguas Residuales
            
            ## Introducción a Hydrous Management Group
            
            Hydrous Management Group es líder en soluciones de tratamiento de agua para clientes industriales. 
            Nuestro enfoque combina tecnología avanzada con diseño personalizado para ofrecer soluciones 
            eficientes y sostenibles.
            
            ## Datos del Cliente
            
            - **Nombre:** Industrias Procesadoras S.A.
            - **Ubicación:** Ciudad de México, México
            - **Sector:** Alimentos y Bebidas
            - **Consumo de agua:** 250 m³/día
            - **Generación de aguas residuales:** 200 m³/día
            
            ## Solución Propuesta
            
            Recomendamos un sistema completo que incluye:
            
            1. Pretratamiento con DAF (Flotación por Aire Disuelto)
            2. Tratamiento biológico MBBR (Reactor de Lecho Móvil)
            3. Filtración multimedia y desinfección UV
            
            ## Presupuesto
            
            - **Inversión inicial:** $350,000 USD
            - **Costo operativo mensual:** $8,500 USD
            
            ## Retorno de Inversión
            
            Con un ahorro mensual estimado de $15,000 USD, el sistema se amortizará en aproximadamente 
            24 meses.
            """

            # Generar PDF simple
            pdf_filename = f"propuesta_simple_{conversation_id}.pdf"
            output_path = os.path.join("uploads", pdf_filename)

            # Configura el documento
            doc = SimpleDocTemplate(output_path, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []

            # Divide el texto en líneas y lo procesa
            for line in proposal_text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                if line.startswith("# "):
                    elements.append(Paragraph(line[2:], styles["Title"]))
                elif line.startswith("## "):
                    elements.append(Paragraph(line[3:], styles["Heading2"]))
                elif line.startswith("- "):
                    elements.append(Paragraph("• " + line[2:], styles["Normal"]))
                else:
                    elements.append(Paragraph(line, styles["Normal"]))

                elements.append(Spacer(1, 6))

            # Construye el PDF
            doc.build(elements)

            return output_path
        except Exception as e:
            logger.error(f"Error generando PDF simple: {e}")
            return None
