import os
import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from weaviate.exceptions import WeaviateQueryError, WeaviateStartUpError, UnexpectedStatusCodeError
from weaviate.collections.collection import Collection
from weaviate.classes.config import Property, DataType, Configure
from weaviate.classes.query import Filter, MetadataQuery
import time

# --- NLTK for sentence tokenization ---
import nltk

load_dotenv()

# --- Credentials ---
weaviate_url = os.environ.get("WEAVIATE_URL")
weaviate_api_key = os.environ.get("WEAVIATE_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")

# --- Prerequisite Checks ---
if not weaviate_url or not weaviate_api_key:
    print("WEAVIATE_URL and WEAVIATE_API_KEY must be set in .env file or environment variables.")
    exit(1)
if not openai_api_key:
    print("Error: OPENAI_API_KEY must be set in your environment for Weaviate's text2vec-openai module.")
    exit(1) 

# --- Weaviate Client Connection ---
try:
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=weaviate_url,
        auth_credentials=Auth.api_key(weaviate_api_key),
        headers={
            "X-OpenAI-Api-Key": openai_api_key
        }
    )
    if not client.is_ready():
        print("Weaviate client connected but not ready. Check Weaviate instance status.")
        exit(1)
    print("Successfully connected to Weaviate Cloud.")
except WeaviateStartUpError as e:
    print(f"Failed to connect to Weaviate: {e}")
    exit(1)

# --- NLTK Punkt Download ---
try:
    nltk.data.find('tokenizers/punkt')
except:
    print("NLTK 'punkt' tokenizer not found. Downloading...")
    try:
        nltk.download('punkt', quiet=True)
        print("'punkt' downloaded successfully.")
    except Exception as e_nltk:
        print(f"Failed to download 'punkt'. Sentence tokenization might be suboptimal. Error: {e_nltk}")


class VectorDatabase:
    @staticmethod
    def get_collection(collection_name: str, model: str = "text-embedding-3-small") -> Collection:
        """
        Retrieves a collection, or creates it configured for Weaviate's text2vec-openai module.
        """
        try:
            str(client.collections.get(collection_name))
            return client.collections.get(collection_name)
        except (WeaviateQueryError, UnexpectedStatusCodeError):
            print(f"Collection '{collection_name}' not found. Creating new collection configured for text2vec-openai.")
            return client.collections.create(
                name=collection_name,
                properties=[
                    Property(name="document_name", data_type=DataType.TEXT, skip_vectorization=True),
                    Property(name="text", data_type=DataType.TEXT), 
                ],
                vectorizer_config=[Configure.NamedVectors.text2vec_openai(
                    name="text_vec",
                    source_properties=["text"],
                    model=model,
                    dimensions=1536
                )]
            )
        except Exception as e:
            print("##################", e)

    def __init__(self, collection_name: str, openai_model: str = "text-embedding-3-small"):
        self.client = client
        
        if not collection_name[0].isupper():
             collection_name = collection_name[0].upper() + collection_name[1:]
        
        # Pass the model name to the collection getter
        self.collection = VectorDatabase.get_collection(collection_name, model=openai_model)
        print(f"VectorDatabase initialized for collection '{self.collection.name}' using '{openai_model}'.")

    def _chunk_by_sentences(self, document_text: str, sentences_per_chunk: int) -> list[str]:
        """Splits text into chunks of N sentences."""
        if not document_text.strip(): return []
        
        try:
            sentences = nltk.sent_tokenize(document_text)
        except Exception:
            sentences = [s.strip() for s in document_text.split('.') if s.strip()]

        chunks = []
        for i in range(0, len(sentences), sentences_per_chunk):
            chunk_sentences = sentences[i:i + sentences_per_chunk]
            chunks.append(" ".join(chunk_sentences))
        
        return chunks

    def update_document(self, document_text: str, document_name: str, sentences_per_chunk: int = 5):
        """
        Deletes old document chunks and inserts new ones, letting Weaviate handle vectorization.
        """
        print(f"\nUpdating document: '{document_name}' using sentence-based chunking.")
        
        # 1. Delete old chunks for this document
        try:
            where_filter = Filter.by_property("document_name").equal(document_name)
            response = self.collection.data.delete_many(where=where_filter)
            print(f"Deleted {response.successful} old chunk(s) for '{document_name}'.")
        except Exception as e:
            print(f"Error deleting old chunks for '{document_name}': {e}.")

        # 2. Create new chunks from the document text
        chunks = self._chunk_by_sentences(document_text, sentences_per_chunk)
        if not chunks:
            print("No chunks were generated from the document text.")
            return
        print(f"Created {len(chunks)} new chunks (each with up to {sentences_per_chunk} sentences).")

        # 3. Prepare data objects (WITHOUT vectors)
        data_objects = []
        for chunk_text in chunks:
            data_objects.append({
                "text": chunk_text,
                "document_name": document_name
            })
            
        # 4. Insert all new chunks into Weaviate. Weaviate will automatically vectorize them.
        print("Inserting new chunks into Weaviate in a batch...")
        try:
            with self.client.batch.dynamic() as batch:
                for obj_properties in data_objects:
                    batch.add_object(
                        collection=self.collection.name, # Specify the collection name here
                        properties=obj_properties
                    )
            # The batch context manager handles the execution automatically upon exit.
            print(f"Successfully added {len(data_objects)} new chunks for '{document_name}'.")
        except Exception as e:
            print(f"An error occurred during Weaviate batch import: {e}")

    def perform_search(self, query: str, num_results: int = 5, document_names_filter: list[str] = None):
        """Performs a vector search using Weaviate's near_text which handles query vectorization."""
        print(f"\n--- Performing vector search for: '{query}' ---")
        
        active_filter = None
        if document_names_filter:
            op = [Filter.by_property("document_name").equal(name) for name in document_names_filter]
            active_filter = Filter.any_of(op)
        
        try:
            # Use near_text to let Weaviate vectorize the query and search
            response = self.collection.query.near_text(
                query=query,
                limit=num_results,
                return_properties=["text", "document_name"],
                return_metadata=MetadataQuery(distance=True),
                filters=active_filter
            )
            return [str(ob) for ob in response.objects] if response else []
        except Exception as e:
            print(f"Error during search: {e}")
            return []


if __name__ == "__main__":
    print("\n--- Starting VectorDatabase Demo (Weaviate's text2vec-openai) ---")
    
    # Instantiate VectorDatabase. No vectorizer class is needed.
    db_collection_name = "Test_space_2"
    # print(VectorDatabase.get_collection(db_collection_name))
    try:
        
        # We can specify the model to use here, which gets passed to Weaviate
        vector_db = VectorDatabase(
            collection_name=db_collection_name, 
            openai_model="text-embedding-3-small"
        )

        # Example Documents
        doc1_name = "SpaceExploration"
        doc1_text = ("The James Webb Space Telescope (JWST) is a large infrared telescope with a 6.5-meter primary mirror. "
                     "JWST was launched on December 25, 2021. It is the successor to the Hubble Space Telescope. "
                     "Its primary mission is to study the early universe, the formation of galaxies, stars, and planets. "
                     "The telescope is located at the Sun-Earth L2 Lagrange point, about 1.5 million kilometers from Earth. "
                     "This location helps keep the telescope cold and stable, which is crucial for infrared astronomy. "
                     "One of its key instruments is the Near-Infrared Camera (NIRCam). Another is the Mid-Infrared Instrument (MIRI).")
        
        doc2_name = "PythonHistory"
        doc2_text = ("Python is an interpreted, high-level, general-purpose programming language. "
                     "Created by Guido van Rossum and first released in 1991. "
                     "Python's design philosophy emphasizes code readability with its notable use of significant whitespace. "
                     "Its language constructs aim to help programmers write clear, logical code. "
                     "Python is dynamically typed and garbage-collected. It supports multiple programming paradigms. "
                     "The name 'Python' was inspired by the British comedy group Monty Python.")

        # Update documents in the database
        vector_db.update_document(doc1_text, doc1_name, sentences_per_chunk=3)
        vector_db.update_document(doc2_text, doc2_name, sentences_per_chunk=3)
        
        print("\nWaiting for indexing (approx 5 seconds)...")
        time.sleep(5) 

        # Perform searches
        search_results_1 = vector_db.perform_search(query="telescope for studying galaxies", num_results=2)
        for i, res in enumerate(search_results_1, 1):
            print(f"  Result {i}: Doc='{res.properties['document_name']}', Distance={res.metadata.distance:.4f}")
            print(f"    Text: '{res.properties['text']}'")

        search_results_2 = vector_db.perform_search(query="who created python programming language", num_results=2)
        for i, res in enumerate(search_results_2, 1):
            print(f"  Result {i}: Doc='{res.properties['document_name']}', Distance={res.metadata.distance:.4f}")
            print(f"    Text: '{res.properties['text']}'")

        # Optional: Delete collection for a clean slate on next run
        # print(f"\n--- Deleting collection '{db_collection_name}' (Commented out) ---")
        # client.collections.delete(db_collection_name)

    except Exception as e:
        print(f"\nAn error occurred in the main execution block: {e}")
    finally:
        if 'client' in locals() and client.is_connected():
            client.close()
            print("\nWeaviate client closed.")
    
    print("\n--- Demo Finished ---")