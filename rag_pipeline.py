import os
import json

# Using ONLY core modules that are already working in your venv!
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

def setup_rag(resume_text, jd_text):
    """Creates a transient vector store for the current analysis."""
    docs = [
        Document(page_content=resume_text, metadata={"source": "resume"}),
        Document(page_content=jd_text, metadata={"source": "job_description"})
    ]
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = text_splitter.split_documents(docs)
    
    # Downloads model on first run (~80MB)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return FAISS.from_documents(splits, embeddings)

def format_docs(docs):
    """Helper function to format retrieved documents for the prompt."""
    return "\n\n".join(doc.page_content for doc in docs)

def ask_rag(resume_text, jd_text):
    """Main RAG execution logic using modern LCEL (No legacy chains)."""
    try:
        # Explicitly pass API key to avoid validation errors
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            google_api_key=api_key,
            temperature=0.1
        )

        vectorstore = setup_rag(resume_text, jd_text)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

        # Added explicit JSON instructions to ensure Gemini formats correctly
        system_prompt = (
            "You are an expert ATS. Use the retrieved context to analyze the Resume vs JD.\n\n"
            "Context: {context}\n\n"
            "Return ONLY a valid JSON object with the exact keys: "
            "'score' (number), 'missing_skills' (list), 'suggestions' (list), 'analysis' (string)."
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])

        # Modern LCEL Chain - Completely replaces create_retrieval_chain!
        rag_chain = (
            {"context": retriever | format_docs, "input": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

        # Run the analysis
        raw_text = rag_chain.invoke("Compare the resume against the JD requirements.")
        
        # Clean response and parse JSON
        raw_text = raw_text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text.replace("```json", "", 1)
        if raw_text.startswith("```"):
            raw_text = raw_text.replace("```", "", 1)
        if raw_text.endswith("```"):
            raw_text = raw_text[::-1].replace("```"[::-1], "", 1)[::-1]
            
        return json.loads(raw_text.strip())

    except Exception as e:
        print(f"RAG Error: {e}")
        return None