from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-4o-mini",
    input="Escribe una historia en una sentencia corta sobre un unicornio",
)

print(response.output_text)
