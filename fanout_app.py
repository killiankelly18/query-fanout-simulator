# fanout_app.py
import streamlit as st
import google.generativeai as genai
import openai
import requests
from bs4 import BeautifulSoup
import tiktoken
from sklearn.metrics.pairwise import cosine_similarity
import os

# 🔐 Configure API keys from Streamlit Secrets
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
openai.api_key = os.getenv("OPENAI_API_KEY")

# --- Helper functions ---
def fetch_page_text(url):
    html = requests.get(url).text
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(["script", "style"]):
        tag.decompose()
    return ' '.join(soup.stripped_strings)

def chunk_text(text, max_tokens=200):
    enc = tiktoken.encoding_for_model("gpt-4")
    tokens = enc.encode(text)
    return [enc.decode(tokens[i:i+max_tokens]) for i in range(0, len(tokens), max_tokens)]

def generate_entity_and_queries(text):
    model = genai.GenerativeModel("gemini-pro")
    prompt = f"""
You are simulating AI search behavior. Based on the content below:
1. Identify the main ontological entity.
2. Generate 6 diverse follow-up questions (related, implicit, comparative, procedural, statistical).

--- CONTENT START ---
{text[:3000]}
--- CONTENT END ---

Return this format:
ENTITY: <entity>
QUERIES:
1. ...
2. ...
"""
    response = model.generate_content(prompt)
    return response.text

def get_embedding(text):
    return openai.Embedding.create(
        model="text-embedding-3-small",
        input=[text]
    )['data'][0]['embedding']

def assess_coverage(chunks, queries):
    chunk_embeddings = [get_embedding(chunk) for chunk in chunks]
    query_embeddings = [get_embedding(query) for query in queries]

    scores = []
    for qe in query_embeddings:
        max_score = max(cosine_similarity([qe], [ce])[0][0] for ce in chunk_embeddings)
        scores.append(max_score)
    return scores, sum(scores) / len(scores)

def parse_gemini_output(response_text):
    lines = response_text.splitlines()
    entity_line = next((l for l in lines if l.startswith("ENTITY:")), "ENTITY: Unknown")
    entity = entity_line.replace("ENTITY:", "").strip()
    queries = [line.strip("1234567890.- ") for line in lines if line.strip().startswith(tuple("1234567890"))]
    return entity, queries

# --- Streamlit App ---
st.title("🔎 Query Fan-Out Simulator (Gemini + OpenAI)")

url = st.text_input("Enter a webpage URL to analyze")

if st.button("Run Fan-Out Analysis") and url:
    try:
        with st.spinner("Fetching and analyzing content..."):
            text = fetch_page_text(url)
            chunks = chunk_text(text)
            raw_output = generate_entity_and_queries(text)
            entity, queries = parse_gemini_output(raw_output)
            scores, avg_score = assess_coverage(chunks, queries)

        st.markdown(f"### 🎯 Main Entity: `{entity}`")
        st.markdown("#### 💬 Fan-Out Queries:")
        for q, s in zip(queries, scores):
            if s >= 0.75:
                status = "✅ Covered"
            elif s >= 0.5:
                status = "⚠️ Partial"
            else:
                status = "❌ Missed"
            st.markdown(f"- **{q}** — {status} ({s:.2f})")

        st.success(f"📊 Average AI Visibility Score: **{avg_score:.2f}**")

    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
