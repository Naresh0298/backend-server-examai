# app/claude_service.py
import anthropic
import os
import json
import re # Import re for regex operations
from dotenv import load_dotenv
from typing import Dict, Any

from .mongodb_service import MongoDB, get_mongodb_service # Import MongoDB and its dependency function
from fastapi import Depends # Import Depends for dependency injection

# Load environment variables (ensure this is done once in the app's entry point)
load_dotenv()

# Helper function to extract JSON from a code block (assuming it's consistently formatted)
def extract_json_from_code_block(text):
    print("Raw response:\n", text)
    print("***************")
    """
    Extracts and parses JSON from a markdown-style code block like ```json ... ```
    """
    try:
        # Remove Markdown code block fences (``` or ```json)
        cleaned = re.sub(r'^```(?:json)?\n?|```$', '', text.strip(), flags=re.MULTILINE)
        print(f"RAW text is successfully cleaned")
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print("Raw response:\n", text)
        raise ValueError(f"Invalid JSON response from Claude: {e}")


class ClaudeService:
    # Accept the MongoDB instance and the collection name for exam papers
    def __init__(self, mongodb_instance: MongoDB, exam_paper_collection_name: str):
        self.api_key = os.getenv("CLAUDE_API_KEY") # Use CLAUDE_API_KEY for Anthropic
        if not self.api_key:
            raise ValueError("CLAUDE_API_KEY environment variable is required for ClaudeService.")
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.db_instance = mongodb_instance
        self.exam_paper_collection_name = exam_paper_collection_name

    async def generate_and_store_exam_paper(self, extracted_text: str) -> Dict[str, Any]:
        """
        Generates an exam paper based on the provided text using Claude
        and inserts the structured response into MongoDB.
        """
        prompt = f"""
        Create a university/school-like exam/test question paper for 50 marks using the provided information to help me master these topics:

        ---
        Provided Information:
        {extracted_text}
        ---

        Please structure the paper clearly with different question types (e.g., multiple choice, short answer, essay).
        Include a clear marking scheme.
        """

        try:
            message =  self.client.messages.create( # Use await here as client.messages.create is async
                model="claude-sonnet-4-20250514", # Ensure this model is available
                max_tokens=2000,
                temperature=0.7,
                system="""
                            You are an industry and academic specialist lecturer with 20 years of experience in teaching students aged 8 to 30.

                            When generating an exam paper, structure your response exactly in this JSON format:

                            ```json
                            {
                            "infront_page": {
                                "title": "University of Alathur",
                                "subject": "Subject Name",
                                "total_marks": 50,
                                "exam_time": "02:00",
                                "description": "Please answer ALL THREE Questions.",
                                "secondary_description": "Use a SEPARATE answerbook for each SECTION."
                            },
                            "questions_data": {
                                "num_of_section": 2,
                                "section_a": {
                                "title": "Section A",
                                "child": 3,
                                "questions": {
                                    "1": "Define AI and explain its importance.",
                                    "2": "What are the types of machine learning?",
                                    "3": "List any two applications of AI."
                                }
                                },
                                "section_b": {
                                "title": "Section B",
                                "child": 2,
                                "questions": {
                                    "1": "Explain supervised vs unsupervised learning with examples.",
                                    "2": "Design a flowchart for a recommendation system."
                                }
                                }
                            }
                            }
                            ```
                            Return only valid JSON, enclosed in triple backticks with ```json.
                        """,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )
            response_text = message.content[0].text
            structured_response = extract_json_from_code_block(response_text)

            if structured_response:
                # Insert the data into MongoDB
                exam_paper_collection = self.db_instance.get_collection(self.exam_paper_collection_name)
                # Ensure the data matches the Pydantic model if you want validation
                # You can convert structured_response to ExamPaper model here if strict validation is needed
                # exam_paper_data = ExamPaper(**structured_response).model_dump() # Use model_dump() for dictionary
                # --- FIX IS HERE: AWAIT THE INSERT_ONE CALL ---
                insert_result = await exam_paper_collection.insert_one(structured_response)
                
                print(f"[DEBUG] Exam paper inserted into MongoDB with ID: {insert_result.inserted_id}")
                return structured_response
            else:
                raise ValueError("Failed to extract valid JSON from Claude's response.")


        except anthropic.APIError as e:
            print(f"Claude API Error: {e}")
            raise RuntimeError(f"Claude API request failed: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during exam paper generation/storage: {e}")
            raise RuntimeError(f"Failed to generate or store exam paper: {e}")

# Dependency injection for ClaudeService
def get_claude_service(
    mongodb_instance: MongoDB = Depends(get_mongodb_service) # Inject MongoDB service
) -> ClaudeService:
    """Dependency injection for ClaudeService."""
    # 'exam_papers' is a good default collection name, but can be made configurable via env var
    return ClaudeService(
        mongodb_instance=mongodb_instance,
        exam_paper_collection_name="exam_papers"
    )

