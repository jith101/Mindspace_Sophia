from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_pymongo import PyMongo
from flask_session import Session
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import bcrypt
import os
import requests
from dotenv import load_dotenv
import re
import numpy as np
from numpy.linalg import norm
from sentence_transformers import SentenceTransformer
from bson import ObjectId

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MONGO_URI'] = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/therapychat')

# Initialize extensions
mongo = PyMongo(app)
Session(app)

# Database collections
users = mongo.db.users
messages = mongo.db.messages

# Initialize sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

def get_embedding(text):
    """Generate embedding for the given text"""
    return model.encode(text).tolist()

def cosine_similarity(a, b):
    """Calculate cosine similarity between two vectors"""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (norm(a) * norm(b) + 1e-8)

def get_semantic_context(user_id, query, top_k=3):
    """
    Retrieve semantically similar messages for the given query
    
    Args:
        user_id: ID of the user
        query: The search query
        top_k: Number of similar messages to return
        
    Returns:
        List of relevant messages
    """
    # Get all user messages
    user_messages = list(messages.find({
        'user_id': user_id,
        'message': {'$exists': True, '$ne': ''}
    }))
    
    if not user_messages:
        return []
    
    # Generate query embedding
    query_embedding = get_embedding(query)
    
    # Calculate similarity scores
    for msg in user_messages:
        if 'embedding' not in msg:
            # Add embedding if not exists
            msg['embedding'] = get_embedding(msg['message'])
            # Update the message with embedding
            messages.update_one(
                {'_id': msg['_id']},
                {'$set': {'embedding': msg['embedding']}}
            )
        
        # Calculate similarity score
        msg['similarity'] = cosine_similarity(query_embedding, msg['embedding'])
    
    # Sort by similarity score (descending)
    relevant_messages = sorted(
        user_messages,
        key=lambda x: x.get('similarity', 0),
        reverse=True
    )
    
    # Return top k messages
    return [{
        'message': msg['message'],
        'is_from_user': msg.get('is_from_user', True),
        'timestamp': msg.get('timestamp', datetime.utcnow()),
        'similarity': msg.get('similarity', 0)
    } for msg in relevant_messages[:top_k]]

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('auth'))

@app.route('/auth')
def auth():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/main_page.html')
def main_page():
    if 'user_id' not in session:
        return redirect('/auth.html')
    
    # Get user data to pass to the template
    user = users.find_one({'_id': ObjectId(session['user_id'])})
    if not user:
        session.clear()
        return redirect('/auth.html')
        
    return render_template('main_page.html', email=session['email'])

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required'}), 400
    
    # Check if user already exists
    if users.find_one({'email': email}):
        return jsonify({'success': False, 'message': 'Email already registered'}), 400
    
    # Hash password
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    # Create new user
    user = {
        'email': email,
        'password': hashed,
        'created_at': datetime.now(timezone.utc)
    }
    
    users.insert_one(user)
    
    # Don't log in automatically, redirect to login
    return jsonify({
        'success': True, 
        'message': 'Registration successful. Please login to continue.',
        'redirect': '/auth.html#login'  # Redirect to login page
    })

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required'}), 400
    
    user = users.find_one({'email': email})
    
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return jsonify({'success': False, 'message': 'Invalid email or password'}), 401
    
    # Set session
    session['user_id'] = str(user['_id'])
    session['email'] = user['email']
    
    return jsonify({
        'success': True, 
        'message': 'Login successful',
        'redirect': '/main_page.html'  # Redirect to main chat page
    })

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'redirect': url_for('auth')})

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('auth'))
    
    # Get user's messages
    user_messages = list(messages.find({'user_id': session['user_id']}).sort('timestamp', 1))
    
    # Convert ObjectId to string for JSON serialization
    for msg in user_messages:
        msg['_id'] = str(msg['_id'])
        msg['user_id'] = str(msg['user_id'])
    
    return render_template('main_page.html', messages=user_messages, email=session['email'])

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    # Check if user is logged in
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    if request.method == 'GET':
        # Get all messages for the user
        try:
            user_messages = list(messages.find({'user_id': user_id}).sort('timestamp', 1))
            
            # Convert ObjectId to string for JSON serialization
            for msg in user_messages:
                msg['_id'] = str(msg['_id'])
                msg['user_id'] = str(msg['user_id'])
                
            return jsonify(user_messages)
        except Exception as e:
            print(f"Error fetching messages: {str(e)}")
            return jsonify({'success': False, 'message': 'Error fetching messages'}), 500
    
    elif request.method == 'POST':
        # Save new message
        try:
            data = request.get_json()
            message_text = data.get('message')
            is_from_user = data.get('is_from_user', True)
            
            if not message_text or not isinstance(message_text, str) or message_text.strip() == '':
                return jsonify({'success': False, 'message': 'Message is required and cannot be empty'}), 400
            
            # Generate embedding for the message
            message_embedding = get_embedding(message_text.strip())
            
            message = {
                'user_id': user_id,
                'message': message_text.strip(),
                'is_from_user': is_from_user,
                'timestamp': datetime.now(timezone.utc),
                'embedding': message_embedding
            }
            
            # Insert message into database
            result = messages.insert_one(message)
            
            if result.inserted_id:
                return jsonify({
                    'success': True, 
                    'message': 'Message saved',
                    'message_id': str(result.inserted_id)
                })
            else:
                return jsonify({'success': False, 'message': 'Failed to save message'}), 500
                
        except Exception as e:
            print(f"Error saving message: {str(e)}")
            return jsonify({'success': False, 'message': 'Error saving message'}), 500

@app.route('/api/semantic-search', methods=['POST'])
def semantic_search():
    """
    Endpoint for semantic search in conversation history
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    query = data.get('query', '')
    top_k = int(data.get('top_k', 3))
    
    if not query:
        return jsonify({'success': False, 'message': 'Query is required'}), 400
    
    try:
        relevant_messages = get_semantic_context(session['user_id'], query, top_k)
        return jsonify({
            'success': True,
            'results': relevant_messages
        })
    except Exception as e:
        print(f"Error in semantic search: {str(e)}")
        return jsonify({'success': False, 'message': 'Error performing semantic search'}), 500

def clean_ai_response(text):
    """Clean up AI response text"""
    if not text:
        return ""
    
    # Remove any trailing quotes and whitespace
    text = text.strip('"\' ')
    
    # Remove any trailing punctuation followed by quotes
    text = re.sub(r'[\s!?.,;:]*"\s*$', '', text)
    
    # Remove any repeated spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Handle escaped characters
    text = text.encode('utf-8').decode('unicode_escape')
    
    # Clean up any remaining backslashes
    text = text.replace('\\', '')
    
    return text

@app.route('/api/ai/response', methods=['POST'])
def get_ai_response():
    try:
        # Log request details
        print("\n=== AI Response Request ===")
        print(f"User ID: {session.get('user_id')}")
        print(f"Request Data: {request.get_json()}")
        
        # Check if user is logged in
        if 'user_id' not in session:
            print("Error: User not logged in")
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
        user_id = session['user_id']
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({'success': False, 'message': 'Message is required'}), 400
            
        # Check for duplicate message in the last 30 seconds
        duplicate_check = messages.find_one({
            'user_id': user_id,
            'message': user_message,
            'is_from_user': True,
            'timestamp': {'$gte': datetime.now(timezone.utc) - timedelta(seconds=30)}
        })
        
        if duplicate_check:
            print("Duplicate message detected, ignoring")
            return jsonify({
                'success': False,
                'message': 'Duplicate message detected',
                'is_duplicate': True
            }), 200
            
        # Get relevant context using semantic search
        context_messages = get_semantic_context(user_id, user_message, top_k=3)
        print(f"Found {len(context_messages)} relevant context messages")

        # Import API key from config
        from config.api_keys import RUNPOD_API_KEY
        
        # Prepare the API request to RunPod AI
        headers = {
            'Content-Type': 'application/json',
            'Authorization': RUNPOD_API_KEY
        }

        try:
            # Get the last few messages for context
            recent_messages = list(messages.find(
                {'user_id': user_id}
            ).sort('timestamp', -1).limit(5))
            print(f"Found {len(recent_messages)} recent messages")
            
            # Build the context string
            context = "\n".join(
                f"{'User' if msg['is_from_user'] else 'Therapist'}: {msg['message']}"
                for msg in recent_messages
            )
            print(f"Context: {context[:200]}...")

            # Prepare the API request
            api_data = {
                'input': {
                    'question': user_message,
                    'context': context,
                    'max_tokens': 200,
                    'temperature': 0.7
                }
            }
            print(f"API Data: {api_data}")

            # Make the API call
            response = requests.post(
                'https://api.runpod.ai/v2/ovzpgfqd38xtyh/runsync',
                headers=headers,
                json=api_data
            )
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"API Response: {result}")
                
                # Extract the response text
                raw_answer = str(result)
                print("Raw response:", raw_answer)
                
                # Try to extract text between 'Answer: [/INST]' and the next quote
                answer_match = re.search(r'Answer:\s*\[\/INST\]\s*([^"]+)', raw_answer)
                if answer_match:
                    ai_response = answer_match.group(1).strip()
                    print(f"Extracted answer: {ai_response}")
                else:
                    # Last resort: try to extract any text between quotes
                    quote_match = re.search(r'"([^"]+)"', raw_answer)
                    if quote_match:
                        ai_response = quote_match.group(1).strip()
                        print(f"Extracted from quotes: {ai_response}")
                    else:
                        ai_response = "I'm here to listen. Could you tell me more about how you're feeling?"
                        print("Using default response")

                # Clean up the response
                ai_response = clean_ai_response(ai_response)
                
                # Check if this message pair already exists in the last minute
                recent_message = messages.find_one({
                    'user_id': user_id,
                    'message': user_message,
                    'timestamp': {'$gte': datetime.now(timezone.utc) - timedelta(minutes=1)}
                })
                
                if recent_message:
                    print("Found recent duplicate message, skipping database save")
                    return jsonify({
                        'success': True,
                        'message': ai_response
                    })
            else:
                error_text = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"API Error {response.status_code}: {error_text}")
                ai_response = "I'm having trouble connecting to my thoughts right now. Could you try again in a moment?"
            
            # Ensure the response isn't empty
            if not ai_response:
                ai_response = "I'm here to listen. Could you tell me more about how you're feeling?"
                print("Empty response, using fallback")

            # Clean up the AI response
            ai_response = clean_ai_response(ai_response)
            
            # Only save if no recent duplicate was found
            current_time = datetime.now(timezone.utc)
            
            # Save both user's question and AI's response in a transaction
            with mongo.cx.start_session() as mongo_session:
                try:
                    # Start a transaction
                    with mongo_session.start_transaction():
                        # Save user's question
                        user_message_doc = {
                            'user_id': user_id,
                            'message': user_message,
                            'is_from_user': True,
                            'timestamp': current_time,
                            'embedding': get_embedding(user_message)
                        }
                        messages.insert_one(user_message_doc, session=mongo_session)
                        print("Saved user message to database")

                        # Save AI's response
                        ai_response_doc = {
                            'user_id': user_id,
                            'message': ai_response,
                            'is_from_user': False,
                            'timestamp': current_time,
                            'embedding': get_embedding(ai_response)
                        }
                        messages.insert_one(ai_response_doc, session=mongo_session)
                        print("Saved AI response to database")
                        
                except Exception as e:
                    print(f"Error in transaction: {str(e)}")
                    mongo_session.abort_transaction()
                    raise

            return jsonify({
                'success': True,
                'message': ai_response
            })
            
        except Exception as e:
            print(f"Error in API processing: {str(e)}")
            raise
            
    except Exception as e:
        print(f"=== Final Error ===")
        print(f"Error in get_ai_response: {str(e)}")
        import traceback
        print("=== Full Traceback ===")
        print(traceback.format_exc())
        
        return jsonify({
            'success': False,
            'message': "I'm having some trouble understanding right now. Could you rephrase that or try again in a moment?"
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
