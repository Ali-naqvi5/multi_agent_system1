import uuid
from graph.orchestrator import run_pipeline

def main():
    print("\n" + "="*60)
    print("  PAST PAPER RETRIEVAL SYSTEM")
    print("="*60 + "\n")

    user_query = input("  What papers would you like to find? ").strip()
    thread_id = str(uuid.uuid4())[:8]
    run_pipeline(user_query=user_query, thread_id=thread_id)

if __name__ == "__main__":
    main()































