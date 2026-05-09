"""
ChromaDB Initialization Script for SWAT RAG Service
====================================================
This script initializes the ChromaDB vector database with SWAT system knowledge.

Run this ONCE after installing requirements:
    python initialize_chromadb.py

Location: D:\FYP - FINAL\Dashboard\PythonRagService\
"""

import chromadb
from chromadb.config import Settings
import os

def initialize_chromadb():
    """Initialize ChromaDB with SWAT knowledge base"""
    
    print("=" * 60)
    print("ChromaDB Initialization for SWAT RAG Service")
    print("=" * 60)
    
    # Get current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    chroma_db_path = os.path.join(current_dir, "chroma_db")
    
    print(f"ChromaDB path: {chroma_db_path}")
    
    # Create ChromaDB client
    try:
        client = chromadb.PersistentClient(
            path=chroma_db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        print("✅ ChromaDB client created")
    except Exception as e:
        print(f"❌ Error creating ChromaDB client: {e}")
        return False
    
    # Create or get collection
    try:
        # Delete existing collection if it exists (for clean initialization)
        try:
            client.delete_collection("swat_knowledge")
            print("🗑️  Deleted existing collection")
        except:
            pass
        
        collection = client.create_collection(
            name="swat_knowledge",
            metadata={"description": "SWAT SCADA system knowledge base"}
        )
        print("✅ Collection 'swat_knowledge' created")
    except Exception as e:
        print(f"❌ Error creating collection: {e}")
        return False
    
    # Knowledge documents to embed
    knowledge_documents = [
        {
            "id": "schema_main",
            "text": """
            Database Schema for SWAT System:
            
            Table: raw_plant_data
            - id (int, PRIMARY KEY, IDENTITY): Unique record identifier
            - ts (datetime2): Timestamp of data collection
            - plant_id (nvarchar(50)): Plant/system identifier
            - payload_json (nvarchar(MAX)): JSON containing all sensor and actuator data
            
            JSON Structure in payload_json:
            {
                // Actuator States (0=OFF, 1=ON, 2=AUTO)
                "P101": 2, "P201": 2, "P203": 2, "P205": 2, 
                "P302": 2, "P402": 2, "P403": 2, "P501": 2,
                "MV101": 2, "MV201": 2, "MV301": 2, "MV302": 2,
                "MV303": 2, "MV304": 2,
                
                // Sensor Readings (16 sensors)
                "true_FIT101": 2.48,  // Flow sensors (FIT)
                "true_FIT201": 2.45,
                "true_FIT301": 2.21,
                "true_FIT401": 1.72,
                "true_FIT501": 1.74,
                "true_LIT101": 503.13,  // Level sensors (LIT)
                "true_LIT301": 914.43,
                "true_LIT401": 860.85,
                "true_AIT201": 175.95,  // Analog sensors (AIT)
                "true_AIT202": 8.61,
                "true_AIT203": 301.97,
                "true_AIT401": 148.86,
                "true_AIT402": 142.68,
                "true_AIT501": 7.76,
                "true_DPIT301": 20.14,  // Differential pressure
                "true_PIT501": 247.22,  // Pressure
                
                // Motor Health (24 features: 8 pumps × 3 metrics)
                "true_P101_motor_temp": 42.22,
                "true_P101_current": 2.55,
                "true_P101_vibration": 0.96,
                // ... (repeated for P201, P203, P205, P302, P402, P403, P501)
                
                // System Status
                "timestamp": "2026-01-26T12:00:00",
                "system_status": "RUN"
            }
            
            SQL Query Examples:
            - Extract sensor value: JSON_VALUE(payload_json, '$.true_FIT101')
            - Filter by time: WHERE ts >= DATEADD(hour, -1, GETDATE())
            - Order by time: ORDER BY ts ASC
            """,
            "metadata": {"type": "database_schema", "category": "technical"}
        },
        {
            "id": "components_pumps",
            "text": """
            SWAT Water Treatment System - Pump Components:
            
            P101: Primary Intake Pump (Stage 1)
            - Function: Draws raw water from source
            - Normal operation: Continuous during RUN mode
            - Normal motor temp: 38-44°C
            - Normal current: 2.0-3.0A
            - Normal vibration: 0.8-1.2
            
            P201, P203, P205: Chemical Dosing Pumps (Stage 2)
            - P201: NaCl (Sodium Chloride) dosing
            - P203: HCl (Hydrochloric Acid) dosing for pH control
            - P205: NaOCl (Sodium Hypochlorite) dosing for disinfection
            - Normal motor temp: 38-45°C
            - Normal current: 4.5-5.5A
            - Normal vibration: 1.3-1.6
            
            P302: Ultrafiltration Feed Pump (Stage 3)
            - Function: Pushes water through UF membrane
            - High pressure operation
            - Normal motor temp: 40-46°C
            - Normal current: 5.5-7.0A
            - Normal vibration: 1.5-1.9
            - Critical component: UF membrane clogging affects performance
            
            P402, P403: Dechlorination Pumps (Stage 4)
            - P402: UV pre-treatment feed
            - P403: NaHSO₄ (Sodium Bisulfate) dosing for dechlorination
            - Normal motor temp: 36-42°C
            - Normal current: 4.0-5.0A
            - Normal vibration: 1.2-1.5
            
            P501: Reverse Osmosis Feed Pump (Stage 5)
            - Function: High-pressure feed to RO membrane
            - Highest pressure in system
            - Normal motor temp: 36-42°C
            - Normal current: 3.5-4.5A
            - Normal vibration: 1.0-1.3
            
            General Pump Health Indicators:
            - Temperature > 45°C: Warning
            - Temperature > 50°C: Critical
            - Vibration > 1.5: Warning
            - Vibration > 2.0: Critical
            - Current deviation > 20% from normal: Warning
            
            Common Pump Issues:
            - High temp + High vibration: Bearing wear
            - High temp + High current: Motor overload
            - High vibration only: Misalignment or cavitation
            - High current only: Increased load (clogging, blockage)
            """,
            "metadata": {"type": "component_info", "category": "pumps"}
        },
        {
            "id": "components_sensors",
            "text": """
            SWAT Sensor Types and Naming Convention:
            
            SENSOR TYPE CODES:
            - FIT: Flow Indicator Transmitter (measures flow rate in L/min)
            - LIT: Level Indicator Transmitter (measures tank level in mm)
            - PIT: Pressure Indicator Transmitter (measures pressure in kPa)
            - DPIT: Differential Pressure Indicator Transmitter
            - AIT: Analog Indicator Transmitter (various measurements)
            
            NAMING CONVENTION: [TYPE][STAGE][NUMBER]
            Examples:
            - FIT101: Flow sensor in Stage 1, sensor #1
            - LIT301: Level sensor in Stage 3, sensor #1
            - AIT201: Analog sensor in Stage 2, sensor #1
            
            STAGE MAPPING:
            - Stage 1 (100 series): Raw water intake
            - Stage 2 (200 series): Chemical treatment
            - Stage 3 (300 series): Ultrafiltration
            - Stage 4 (400 series): Dechlorination and UV treatment
            - Stage 5 (500 series): Reverse osmosis
            
            KEY SENSORS:
            
            FIT101 (Stage 1 Flow):
            - Measures intake flow rate
            - Normal range: 2.0-2.8 L/min
            - Critical for system startup
            
            LIT101 (Stage 1 Level):
            - Raw water tank level
            - Normal range: 400-600 mm
            - Low level triggers intake pump
            
            FIT201 (Stage 2 Flow):
            - Chemical treatment stage flow
            - Should match FIT101 (minor loss acceptable)
            
            AIT201, AIT202, AIT203 (Stage 2 Chemistry):
            - AIT201: Conductivity (150-200 μS/cm typical)
            - AIT202: pH level (6.5-8.5 target range)
            - AIT203: ORP (Oxidation-Reduction Potential) for chlorine monitoring
            
            DPIT301 (Stage 3 Differential Pressure):
            - Measures pressure drop across UF membrane
            - Normal: 10-30 kPa
            - High DPIT (>40 kPa): Membrane fouling
            - Triggers backwash cycle
            
            LIT301 (Stage 3 UF Tank Level):
            - Filtered water storage
            - Normal: 800-1000 mm
            
            FIT401, AIT401, AIT402 (Stage 4):
            - FIT401: Flow through UV system
            - AIT401: UV transmittance
            - AIT402: Post-dechlorination ORP
            
            PIT501, FIT501, AIT501 (Stage 5 RO):
            - PIT501: RO feed pressure (200-300 kPa)
            - FIT501: Permeate flow rate
            - AIT501: Product water TDS (Total Dissolved Solids)
            
            LIT401 (Stage 4 Clearwell):
            - Final treated water storage
            - Normal: 700-900 mm
            """,
            "metadata": {"type": "sensor_info", "category": "sensors"}
        },
        {
            "id": "ml_models",
            "text": """
            Machine Learning Inference System (Port 5000):
            
            THREE-STAGE PIPELINE:
            
            STAGE 1: Anomaly Detection
            - Purpose: Binary classification (Normal vs Anomaly)
            - Models available: Autoencoder, DAE, LOF, Isolation Forest, XGBoost
            - Input: 40 features (16 sensors + 24 motor health metrics)
            - Output: 
              * is_anomaly (boolean)
              * confidence (0.0-1.0)
              * anomaly_score (varies by model)
            - Buffer requirement: None (single sample)
            - Typical confidence: >0.7 for reliable detection
            
            STAGE 2: State Classification
            - Purpose: Multi-class classification (only runs if Stage 1 detects anomaly)
            - Models available: LSTM, CNN, XGBoost
            - States: NORMAL, ANOMALY, DEGRADING, FAULTED
            - Input: 
              * Temporal models (LSTM/CNN): 60-sample sequence
              * Tabular models (XGBoost): Single sample
            - Output:
              * state (string)
              * confidence (0.0-1.0)
              * state probabilities for all classes
            - Buffer requirement: 60 samples for LSTM/CNN
            - State meanings:
              * NORMAL: No issues detected
              * ANOMALY: Deviation detected, cause unclear
              * DEGRADING: Performance declining, maintenance soon
              * FAULTED: Component failure, immediate action required
            
            STAGE 3: Component Identification
            - Purpose: Identify which component is faulty (only runs if Stage 2 is DEGRADING or FAULTED)
            - Models available: MLP, LightGBM, XGBoost
            - Components: P101, P201, P203, P205, P302, P402, P403, P501, MV101, MV304
            - Output:
              * component (string): Most likely faulty component
              * confidence (0.0-1.0)
              * top3: List of [(component, confidence)] for top 3 suspects
            - Decision making:
              * Confidence >0.7: High certainty
              * Confidence 0.5-0.7: Moderate certainty
              * Confidence <0.5: Low certainty (investigate multiple components)
            
            RECOMMENDED ACTIONS (from ML API):
            The ML API returns component-specific maintenance actions:
            
            Example for P302:
            - 🔧 Inspect UF feed pump P302
            - 📋 Check UF membrane differential pressure
            - 💧 Consider membrane backwash or cleaning
            
            Actions include emojis for easy visual identification:
            - 🔧: Mechanical inspection
            - 📋: Measurement/monitoring
            - 💧: Fluid system check
            - ⚗️: Chemical system check
            - ⚙️: Actuator/valve check
            
            BUFFER STATUS:
            - Buffer size: 60 samples
            - Buffer ready: true when 60 samples collected
            - Using buffer: true if LSTM/CNN models are active
            - Buffer reset: Triggered on offline→online transition
            
            API ENDPOINTS:
            - POST /api/inference: Single sample inference
            - POST /api/inference/batch: Batch processing
            - POST /api/buffer/reset: Clear buffer
            - GET /api/buffer/status: Check buffer state
            - GET /health: Service health check
            
            PERFORMANCE NOTES:
            - Inference time: 100-200ms per sample
            - Models cached at startup (no reload overhead)
            - GPU acceleration if available
            - CPU fallback for compatibility
            """,
            "metadata": {"type": "ml_info", "category": "predictive"}
        }
    ]
    
    # Add documents to ChromaDB
    print(f"✅ Embedding {len(knowledge_documents)} knowledge documents...")
    
    try:
        for doc in knowledge_documents:
            collection.add(
                documents=[doc["text"]],
                ids=[doc["id"]],
                metadatas=[doc["metadata"]]
            )
            print(f"✅ Document '{doc['id']}' embedded (384 dimensions)")
        
        # Verify collection
        count = collection.count()
        print(f"✅ ChromaDB ready! Total documents: {count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding documents: {e}")
        return False


def test_vector_search():
    """Test vector search functionality"""
    
    print("\n" + "=" * 60)
    print("Testing ChromaDB Vector Search")
    print("=" * 60)
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    chroma_db_path = os.path.join(current_dir, "chroma_db")
    
    try:
        client = chromadb.PersistentClient(path=chroma_db_path)
        collection = client.get_collection("swat_knowledge")
        
        # Test query
        test_query = "What pumps are in stage 2?"
        print(f"\nTest Query: '{test_query}'")
        
        results = collection.query(
            query_texts=[test_query],
            n_results=2
        )
        
        if results['documents'] and len(results['documents'][0]) > 0:
            print(f"\nTop Result (truncated):")
            top_result = results['documents'][0][0][:200]
            print(f"{top_result}...")
            print("\n✅ ChromaDB vector search working correctly!")
            return True
        else:
            print("❌ No results returned")
            return False
            
    except Exception as e:
        print(f"❌ Error testing vector search: {e}")
        return False


if __name__ == "__main__":
    # Initialize ChromaDB
    success = initialize_chromadb()
    
    if success:
        # Test vector search
        test_vector_search()
        print("\n" + "=" * 60)
        print("ChromaDB initialization complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Start Ollama: ollama serve")
        print("2. Verify Mistral model: ollama list")
        print("3. Test RAG service: python rag_api.py")
        print("=" * 60)
    else:
        print("\n❌ ChromaDB initialization failed")
        print("Check error messages above for details")
