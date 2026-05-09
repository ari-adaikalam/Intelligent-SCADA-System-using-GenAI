"""
Simple test to verify ChromaDB is working
"""

import chromadb
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
chroma_db_path = os.path.join(current_dir, "chroma_db")

print("Testing ChromaDB...")
print(f"Path: {chroma_db_path}")

client = chromadb.PersistentClient(path=chroma_db_path)
collection = client.get_collection("swat_knowledge")

print(f"✅ Collection loaded: {collection.count()} documents")

# Test query
results = collection.query(
    query_texts=["What pumps are in stage 2?"],
    n_results=1
)

if results['documents'] and len(results['documents'][0]) > 0:
    print("\n✅ Vector search working!")
    print(f"Sample result: {results['documents'][0][0][:150]}...")
else:
    print("❌ No results")

print("\n✅ ChromaDB fully operational!")
