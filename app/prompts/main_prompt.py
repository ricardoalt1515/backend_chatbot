import os


def get_master_prompt():
    """Carga y combina el prompt maestro con el cuestionario"""
    # Cargar el PROMPT.md original
    prompt_path = os.path.join(os.path.dirname(__file__), "PROMPT.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    # Cargar el cuestionario
    questionnaire_path = os.path.join(os.path.dirname(__file__), "questionnaire.json")
    with open(questionnaire_path, "r", encoding="utf-8") as f:
        questionnaire_data = json.load(f)

    # Formatear las preguntas del cuestionario para un sector específico (podemos empezar con textil)
    questionnaire_text = "# CUESTIONARIO COMPLETO\n\n"
    if "questions" in questionnaire_data:
        sector_key = "Industrial_Textil"  # Por defecto usamos textil
        if sector_key in questionnaire_data["questions"]:
            questionnaire_text += "## Preguntas para el sector textil:\n\n"
            for idx, question in enumerate(
                questionnaire_data["questions"][sector_key], 1
            ):
                questionnaire_text += f"{idx}. **{question['text']}**\n"
                if question["type"] == "multiple_choice" and "options" in question:
                    for opt_idx, option in enumerate(question["options"], 1):
                        questionnaire_text += f"   {opt_idx}. {option}\n"
                questionnaire_text += (
                    f"   *Explicación: {question.get('explanation', '')}*\n\n"
                )

    # Formatear hechos educativos por sector
    facts_text = "# DATOS EDUCATIVOS POR SECTOR\n\n"
    if "facts" in questionnaire_data:
        for sector, facts in questionnaire_data["facts"].items():
            facts_text += f"## {sector}:\n"
            for fact in facts:
                facts_text += f"- *{fact}*\n"
            facts_text += "\n"

    # Combinar todo
    complete_prompt = f"{prompt_text}\n\n{questionnaire_text}\n\n{facts_text}"

    return complete_prompt
