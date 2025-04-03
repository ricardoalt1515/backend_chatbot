from typing import List, Dict, Any
import fpdf
from datetime import datetime


def generate_proposal_pdf(conversation_history: List[Dict[str, Any]], output_path: str):
    """
    Genera un PDF de propuesta basado en el historial de conversación.
    """
    # Crear PDF
    pdf = fpdf.FPDF(format="A4")
    pdf.add_page()

    # Fuentes y estilos
    pdf.set_font("Arial", "B", 16)

    # Encabezado
    pdf.cell(0, 10, "Hydrous Management Group", ln=True, align="C")
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Propuesta de Tratamiento de Aguas Residuales", ln=True, align="C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 10, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=True)
    pdf.ln(10)

    # Información legal
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "Importante: Documento generado por IA", ln=True)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(
        0,
        5,
        "Esta propuesta fue generada utilizando Inteligencia Artificial basada en la información proporcionada. Las estimaciones y recomendaciones deben ser validadas por especialistas antes de su implementación.",
    )
    pdf.ln(10)

    # Extraer respuestas del cuestionario
    # (Aquí procesaríamos el historial para presentar los datos de forma estructurada)

    # Secciones de la propuesta
    sections = [
        "Introducción al Grupo de Gestión Hidráulica",
        "Antecedentes del proyecto",
        "Objetivo del Proyecto",
        "Supuestos clave de diseño",
        "Diseño de Procesos y Alternativas de Tratamiento",
        "Equipo y tamaño sugeridos",
        "Estimación de CAPEX y OPEX",
        "Análisis del retorno de la inversión (ROI)",
    ]

    # Generar contenido de cada sección
    for section in sections:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, section, ln=True)
        pdf.set_font("Arial", "", 10)
        pdf.multi_cell(
            0,
            5,
            "Contenido de muestra para esta sección basado en las respuestas recopiladas durante el cuestionario.",
        )
        pdf.ln(5)

    # Guardar PDF
    pdf.output(output_path)
