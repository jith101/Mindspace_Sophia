import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

def clear_messages():
    try:
        # Get MongoDB URI from environment variables or use default
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/therapychat')
        
        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        
        # Get the database and collection
        db = client.get_database()
        messages = db.messages
        
        # Delete all documents in the messages collection
        result = messages.delete_many({})
        
        print(f"Successfully deleted {result.deleted_count} messages from the database.")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        # Close the connection
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    # Ask for confirmation before deleting
    confirmation = input("WARNING: This will delete ALL messages. Are you sure? (yes/no): ")
    if confirmation.lower() == 'yes':
        clear_messages()
    else:
        print("Operation cancelled.")
