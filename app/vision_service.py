from google.cloud import vision
import io
import json

class VisionService:
    """
    A service class to interact with Google Cloud Vision AI for OCR.
    """
    def __init__(self):
        """
        Initializes the VisionService client.
        The client will automatically use credentials set via
        GOOGLE_APPLICATION_CREDENTIALS environment variable.
        """
        self.client = vision.ImageAnnotatorClient()

    def detect_document_text(self, image_data: bytes):
        """
        Detects dense text from an image using DOCUMENT_TEXT_DETECTION.
        This is suitable for scanned documents like exam papers.

        Args:
            image_data (bytes): The raw bytes of the image file.

        Returns:
            dict: A dictionary containing the full extracted text and
                  structured page/block/paragraph/word information.
                  Returns None if no text is detected or on error.
        """
        try:
            image = vision.Image(content=image_data)
            response = self.client.document_text_detection(image=image)
            
            # Extract full text
            full_text = response.full_text_annotation.text if response.full_text_annotation else ""

            # Extract structured data
            pages_data = []
            if response.full_text_annotation and response.full_text_annotation.pages:
                for page in response.full_text_annotation.pages:
                    blocks_data = []
                    for block in page.blocks:
                        paragraphs_data = []
                        for paragraph in block.paragraphs:
                            words_data = []
                            for word in paragraph.words:
                                word_text = ''.join([symbol.text for symbol in word.symbols])
                                words_data.append({
                                    "text": word_text,
                                    "confidence": word.confidence,
                                    "bounding_box": [(v.x, v.y) for v in word.bounding_box.vertices]
                                })
                            paragraphs_data.append({
                                "text": ''.join([symbol.text for word in paragraph.words for symbol in word.symbols]),
                                "confidence": paragraph.confidence,
                                "words": words_data
                            })
                        blocks_data.append({
                            "text": ''.join([symbol.text for paragraph in block.paragraphs for word in paragraph.words for symbol in word.symbols]),
                            "confidence": block.confidence,
                            "paragraphs": paragraphs_data
                        })
                    pages_data.append({
                        "blocks": blocks_data,
                        "width": page.width,
                        "height": page.height
                    })

            return {
                "full_text": full_text,
                "structured_data": pages_data,
                "error": response.error.message if response.error.message else None
            }

        except Exception as e:
            print(f"Error during Vision AI OCR: {e}")
            return {"full_text": "", "structured_data": [], "error": str(e)}

    def detect_text(self, image_data: bytes):
        """
        Detects general text from an image using TEXT_DETECTION.
        Suitable for sparser text, like signs or labels.

        Args:
            image_data (bytes): The raw bytes of the image file.

        Returns:
            dict: A dictionary containing the detected text and annotations.
                  Returns None if no text is detected or on error.
        """
        try:
            image = vision.Image(content=image_data)
            response = self.client.text_detection(image=image)
            texts = response.text_annotations

            extracted_texts = []
            if texts:
                # The first annotation is the entire text detected in the image
                full_text_description = texts[0].description
                
                # Subsequent annotations are individual words or text blocks
                for text in texts[1:]: # Skip the first element as it's the full text
                    extracted_texts.append({
                        "text": text.description,
                        "bounding_box": [(v.x, v.y) for v in text.bounding_box.vertices]
                    })
            
            return {
                "full_text": full_text_description if texts else "",
                "annotations": extracted_texts,
                "error": response.error.message if response.error.message else None
            }

        except Exception as e:
            print(f"Error during Vision AI TEXT_DETECTION: {e}")
            return {"full_text": "", "annotations": [], "error": str(e)}



#-----PDF-----
    def process_pdf_from_gcs(self, gcs_source_uri: str, gcs_destination_uri: str):
        """
        Performs async OCR on a PDF stored in GCS and writes JSON results to GCS.
        """
        try:
            # Set up input and output configs
            input_config = vision.InputConfig(
                gcs_source=vision.GcsSource(uri=gcs_source_uri),
                mime_type="application/pdf"
            )
            output_config = vision.OutputConfig(
                gcs_destination=vision.GcsDestination(uri=gcs_destination_uri),
                batch_size=2  # Optional: number of pages per JSON output
            )

            # Set the feature to DOCUMENT_TEXT_DETECTION
            feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

            # Construct the request
            async_request = vision.AsyncAnnotateFileRequest(
                features=[feature],
                input_config=input_config,
                output_config=output_config
            )

            print(f"Submitting async OCR job for {gcs_source_uri}...")
            operation = self.client.async_batch_annotate_files(requests=[async_request])

            print("Waiting for async operation to complete...")
            result = operation.result(timeout=600)  # Increase timeout for large files

            print(f"Async OCR completed. Output written to: {gcs_destination_uri}")

            return {
                "gcs_output_uri": gcs_destination_uri,
                "status": "completed",
                "error": None
            }

        except Exception as e:
            print(f"Error during Vision AI PDF OCR: {e}")
            return {
                "gcs_output_uri": None,
                "status": "failed",
                "error": str(e)
            }


    # ... (your read_ocr_results_from_gcs method, which remains the same) ...
    def read_ocr_results_from_gcs(self, gcs_output_uri_prefix: str, bucket_name: str):
        """
        Reads and combines OCR results from the JSON files generated by batch_annotate_files.

        Args:
            gcs_output_uri_prefix (str): The GCS URI prefix where OCR results were written
                                         (e.g., "gs://your-output-bucket/output_prefix/").
            bucket_name (str): The name of the GCS bucket where the output files are stored.

        Returns:
            dict: Combined OCR results (full_text and structured_data) from all pages.
        """
        from google.cloud import storage
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)

        full_text_combined = []
        pages_data_combined = []

        # The prefix should exclude gs:// and the bucket name
        prefix = gcs_output_uri_prefix.replace(f"gs://{bucket_name}/", "")
        
        # List blobs with the given prefix
        # Ensure the prefix ends with a "/" for proper folder listing
        if not prefix.endswith('/'):
            prefix += '/'

        blobs = bucket.list_blobs(prefix=prefix)
        
        # Filter for actual JSON result files, not just directories
        json_blobs = [b for b in blobs if b.name.endswith(".json")]

        if not json_blobs:
            print(f"No OCR result JSON files found under prefix: {gcs_output_uri_prefix}")
            return {
                "full_text": "",
                "structured_data": [],
                "error": "No OCR result files found."
            }

        for blob in json_blobs:
            try:
                print(f"Downloading OCR result file: {blob.name}")
                json_data = blob.download_as_text()
                response_json = json.loads(json_data)
                
                # Each JSON file can contain results for multiple pages (batch_size)
                # The structure is usually 'responses' which is a list of page annotations
                for res in response_json.get("responses", []):
                    if "fullTextAnnotation" in res:
                        # Extract full text for the page
                        full_text_combined.append(res["fullTextAnnotation"]["text"])

                        # Reconstruct structured data for the page
                        page_annotation = res["fullTextAnnotation"]
                        if "pages" in page_annotation:
                            for page_data in page_annotation["pages"]:
                                blocks_data = []
                                for block_data in page_data.get("blocks", []):
                                    paragraphs_data = []
                                    for paragraph_data in block_data.get("paragraphs", []):
                                        words_data = []
                                        for word_data in paragraph_data.get("words", []):
                                            word_text = ''.join([s.get('text', '') for s in word_data.get('symbols', [])])
                                            words_data.append({
                                                "text": word_text,
                                                "confidence": word_data.get("confidence"),
                                                "bounding_box": [(v.get('x'), v.get('y')) for v in word_data.get('boundingBox', {}).get('vertices', [])]
                                            })
                                        paragraphs_data.append({
                                            "text": ''.join([s.get('text', '') for w in paragraph_data.get('words', []) for s in w.get('symbols', [])]),
                                            "confidence": paragraph_data.get("confidence"),
                                            "words": words_data
                                        })
                                    blocks_data.append({
                                        "text": ''.join([s.get('text', '') for p in block_data.get('paragraphs', []) for w in p.get('words', []) for s in w.get('symbols', [])]),
                                        "confidence": block_data.get("confidence"),
                                        "paragraphs": paragraphs_data
                                    })
                                pages_data_combined.append({
                                    "blocks": blocks_data,
                                    "width": page_data.get("width"),
                                    "height": page_data.get("height")
                                })
            except json.JSONDecodeError as jde:
                print(f"Error decoding JSON from blob {blob.name}: {jde}")
                # You might want to skip this file or log a specific error
            except Exception as read_e:
                print(f"Error reading or processing OCR result from blob {blob.name}: {read_e}")


        return {
            "full_text": "\n".join(full_text_combined),
            "structured_data": pages_data_combined,
            "error": None
        }

