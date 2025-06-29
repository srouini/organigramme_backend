
import os
import base64
import io
from xhtml2pdf import pisa
from django.template.loader import get_template
from django.conf import settings


def link_callback(uri, rel):
    """
    Convert HTML links to absolute paths for xhtml2pdf
    
    Args:
        uri (str): URI to convert
        rel (str): Relative path
        
    Returns:
        tuple: (path to file, boolean indicating if file exists)
    """
    # Handle absolute paths
    if uri.startswith('/'):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace('/', '', 1))
        return path
    
    # Handle relative paths
    if uri.startswith('media/'):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace('media/', '', 1))
        return path
        
    # Handle file:// paths with both forward and backward slashes
    if uri.startswith('file://') or uri.startswith('file:///'):        
        # Remove the 'file://' or 'file:///' prefix and normalize slashes
        path = uri.replace('file://', '')
        if path.startswith('/'):
            path = path[1:]
            
        # Normalize path separators (important for Windows paths)
        path = os.path.normpath(path)
        
        if os.path.exists(path):
            return path
        else:
            print(f"Warning: File not found at normalized path: {path}")
    
    # Default case - return the URI as is
    return uri
# Utility function to generate PDF from HTML template
def generate_pdf_from_template(template_name, context, encoding='utf-8'):
    """
    Generate a PDF from an HTML template
    
    Args:
        template_name (str): Name of the template file to use
        context (dict): Context data for template rendering
        encoding (str): Character encoding for the PDF (default: utf-8)
        
    Returns:
        tuple: (pdf_content, error_message)
            pdf_content is the base64 encoded PDF content
            error_message is None if successful, otherwise contains the error message
    """
    try:
        # Get the template
        template = get_template(template_name)
        
        # Render the template with context
        html_content = template.render(context)
        
        # Generate PDF using xhtml2pdf
        pdf_file = io.BytesIO()
        pdf = pisa.CreatePDF(
            src=html_content, 
            dest=pdf_file,
            encoding=encoding,
            link_callback=link_callback  # Add link callback for image paths
        )
        
        if pdf.err:
            return None, f"Error generating PDF: {pdf.err}"
            
        pdf_file.seek(0)
        
        # Encode to base64 for response
        pdf_content = base64.b64encode(pdf_file.read()).decode('utf-8')
        
        return pdf_content, None
    except Exception as e:
        return None, str(e)
