from flask import Flask, request, jsonify, render_template, redirect, url_for, make_response, session
import os
import json
import requests
import datetime
from discord_utils import get_discord_login_url, get_token, get_user_info
import markdown
from openai import OpenAI
import time
import PyPDF2
import base64
import json

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

app = Flask(__name__)
app.secret_key = os.urandom(24)

tokens = {}

@app.route('/')
def index():
  if 'token' in request.cookies:
    token = request.cookies.get('token')
    if token in tokens:
      with open('users.json', 'r') as f:
        users = json.load(f)
      user_info = users[tokens[token]]
      if user_info['name'] == '' or user_info['email'] == '':
        return redirect('/user-onboarding')
      return render_template('user.html', **user_info)
  return render_template('index.html')

@app.route('/user-onboarding')
def user_onboarding():
  if 'token' in request.cookies:
    token = request.cookies.get('token')
    if token in tokens:
      with open('users.json', 'r') as f:
        users = json.load(f)
      user_info = users[tokens[token]]
      return render_template('user-onboarding.html', **user_info)
  return redirect('/')

@app.route('/search', methods=['GET'])
def search():
  query = request.args.get('query')
  if query is None:
    return jsonify({'error': 'query parameter is required'}), 400
  # search colleges.json for colleges that match the query
  with open('colleges.json', 'r') as f:
    colleges = json.load(f)
  results = []
  for college_id in colleges:
    college = colleges[college_id]
    if query.lower() in college['name'].lower():
      results.append(college)
  return render_template('colleges.html', colleges=results)

# Function to summarize transcript (reducing token size)
def summarize_text(text, max_tokens=3000):
    # Summarize the content in smaller chunks
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": "You are an assistant. Summarize the provided transcript into a shorter version that keeps key details."
        },
        {
            "role": "user",
            "content": f"Transcript: {text}"
        }],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

@app.route('/api/get-chance', methods=['POST'])
def get_chance():
    college_id = request.json.get('college_id')
    if college_id is None:
        return jsonify({'error': 'college_id parameter is required'}), 400

    # Load the list of colleges
    with open('colleges.json', 'r') as f:
        colleges = json.load(f)
    if college_id not in colleges:
        return jsonify({'error': 'college not found'}), 404

    college = colleges[college_id]

    # Check for token validity
    token = request.json.get('token')
    if not token or token not in tokens:
        return jsonify({'error': 'invalid token'}), 400

    user_id = tokens[token]
    with open('users.json', 'r') as f:
        users = json.load(f)

    # Get the user data
    user_info = users.get(user_id)
    if not user_info:
        return jsonify({'error': 'user not found'}), 404

    essay = user_info.get('essay')
    transcript_base64 = user_info.get('transcript')
    strictness = request.json.get('strictness', 0.5)

    if not essay or not transcript_base64:
        return jsonify({'error': 'essay or transcript missing'}), 400

    # Convert transcript from base64 to a PDF file
    transcript_pdf_path = "transcript.pdf"
    with open(transcript_pdf_path, "wb") as pdf_file:
        pdf_file.write(base64.b64decode(transcript_base64))

    # Step 1: Extract text content from the transcript PDF using PyPDF2
    with open(transcript_pdf_path, "rb") as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        transcript_content = ""
        for page_num in range(len(reader.pages)):
            transcript_content += reader.pages[page_num].extract_text()

    # Clean up the PDF file
    os.remove(transcript_pdf_path)

    # Step 2: Summarize the transcript to reduce token usage
    summarized_transcript = summarize_text(transcript_content)

    # System prompt that includes strictness considerations
    system_prompt = f'''
    You are an admissions expert evaluating college applications.
    Provide a detailed analysis of the applicant's chances of getting into the specified college based on their essay and transcript.
    Be {strictness * 100}% strict in evaluating them. A strictness value of 1.0 means you will only accept perfect or near-perfect applicants (like a GPA of 5.0 or top SAT scores). A strictness value of 0.0 means you are very lenient, but still reasonable.
    Please output in JSON format with the following fields:
    "chance": (a value between 0.0 and 1.0 indicating the chance of admission),
    "message": (a personalized message regarding the applicant's chance),
    "liked": (a breakdown of things you liked in categories like GPA, extracurriculars, and essay) (include 3),
    "disliked": (a breakdown of things you disliked in categories like SAT score, recommendation letters, and transcript) (include 3).
    '''

    # Create the content for OpenAI
    prompt = f"""
    College: {college['name']}
    Applicant's Essay: {essay}
    Applicant's Transcript: {summarized_transcript}
    Evaluate the applicant's chance of admission to {college['name']} with a strictness value of {strictness}.
    """

    # Step 3: Create the request to analyze the summarized content
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )

    # Step 4: Process OpenAI's response (assuming the response contains a summary and analysis)
    output = response.choices[0].message.content

    # Return the result to the client in the specified JSON format
    return jsonify(json.loads(output))


@app.route('/join')
def join():
  return redirect(get_discord_login_url())

@app.route('/callback')
def callback():
  code = request.args.get('code')
  token_info = get_token(code)
  print(token_info)
  session['discord_token'] = token_info['access_token']
  user_info = get_user_info(session['discord_token'])

  # Write to users.csv
  user_id = user_info['id']
  username = user_info['username']
  avatar = user_info['avatar']

  # check if user exists in users.json
  with open('users.json', 'r') as f:
    users = json.load(f)
  user_info = {
    "name": "",
    "colleges": [],
    "email": user_info.get('email', ''),
    "essay": "",
    "transcript": "",
  }

  if user_id not in users:
    users[user_id] = user_info
    with open('users.json', 'w') as f:
      json.dump(users, f, indent=2)

  session['user_info'] = user_info
  # generate a new token for the user
  token = ''
  while token == '' or token in tokens:
    token = os.urandom(24).hex()
  tokens[token] = user_id
  new_response = make_response(redirect('/'))
  # expire the token in 1 week
  new_response.set_cookie('token', token, max_age=604800)
  # save to tokens.json
  with open('tokens.json', 'w') as f:
    json.dump(tokens, f, indent=2)
  return new_response

@app.route('/api/get_user', methods=['POST'])
def get_user():
  token = request.json.get('token')
  if token is None:
    return jsonify({'error': 'token parameter is required'}), 400
  if token not in tokens:
    return jsonify({'error': 'invalid token'}), 400
  user_id = tokens[token]
  with open('users.json', 'r') as f:
    users = json.load(f)
  user_info = users[user_id]
  return jsonify(user_info)

@app.route('/api/update_user', methods=['POST'])
def update_user():
  token = request.json.get('token')
  if token is None:
    return jsonify
  if token not in tokens:
    return jsonify({'error': 'invalid token'}), 400
  new_user_info = request.json.get('user')
  if new_user_info is None:
    return jsonify({'error': 'user parameter is required'}), 400
  user_id = tokens[token]
  with open('users.json', 'r') as f:
    users = json.load(f)
  users[user_id] = new_user_info
  with open('users.json', 'w') as f:
    json.dump(users, f, indent=2)
  return jsonify({'success': True})

@app.route('/logout')
def logout():
  session.clear()
  response = make_response(redirect('/'))
  response.set_cookie('token', '', expires=0)
  return response

@app.route('/colleges')
def colleges():
  if 'token' not in request.cookies:
    return redirect('/')
  token = request.cookies.get('token')
  if token not in tokens:
    return redirect('/')
  with open('colleges.json', 'r') as f:
    colleges = json.load(f)
  colleges_list = []
  for college in colleges:
    colleges_list.append(colleges[college])
  print(colleges_list)
  return render_template('colleges.html', colleges=colleges_list)

@app.route('/college/<college_id>')
def college(college_id):
  if 'token' not in request.cookies:
    return redirect('/')
  token = request.cookies.get('token')
  if token not in tokens:
    return redirect('/')
  with open('colleges.json', 'r') as f:
    colleges = json.load(f)
  if college_id in colleges:
    return render_template('college.html', college=colleges[college_id])
  else:
    return redirect("/")

@app.route('/api/colleges')
def api_colleges():
  with open('colleges.json', 'r') as f:
    colleges = json.load(f)
  return jsonify(colleges)

@app.route('/api/college/<college_id>')
def api_college(college_id):
  with open('colleges.json', 'r') as f:
    colleges = json.load(f)
  if college_id in colleges:
    return jsonify(colleges[college_id])
  else:
    return jsonify({'error': 'college not found'}), 404

@app.route('/<path:path>')
def catch_all(path):
  # check if path.md exists in markdown folder
  # if it does, render the markdown file
  # otherwise, return 404
  if os.path.exists(f'markdown/{path}.md'):
    with open(f'markdown/{path}.md', 'r') as f:
      content = f.read()
    html_content = markdown.markdown(content)
    print(html_content)
    return render_template('text.html', text=html_content)
  else:
    return redirect("/")

if __name__ == '__main__':
  if os.path.exists('tokens.json'):
    with open('tokens.json', 'r') as f:
      tokens = json.load(f)
  if os.environ.get('DEBUG') == 'TRUE':
    app.run(host='0.0.0.0', port=5000, debug=True)
  else:
    app.run(host='0.0.0.0', port=80, debug=False)