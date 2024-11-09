# Standard library imports
import streamlit as st
import json
from typing import Dict, Optional, List, Union
from datetime import datetime
import logging
import logging.handlers
import os
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
import locale

# Third-party imports
from dotenv import load_dotenv

# Create logs directory if it doesn't exist
try:
    # Define log directory in user's home directory
    LOG_DIR = Path.home() / '.adgenerator' / 'logs'
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOG_DIR / 'adbot.log'

    # Configure logging with rotation
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console handler
            logging.handlers.RotatingFileHandler(
                filename=str(LOG_FILE),
                maxBytes=1024*1024,  # 1MB
                backupCount=5,
                encoding='utf-8'
            )
        ]
    )

except Exception as e:
    # Fallback to basic logging if file handling fails
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logging.warning(f"Failed to setup file logging: {str(e)}. Falling back to console logging.")

# Define supported languages enum
class SupportedLanguage(Enum):
    """
    Enum class for supported languages in the application.
    Most common languages are listed first.
    """
    ENGLISH = 'en'
    SPANISH = 'es'
    MANDARIN = 'zh'
    HINDI = 'hi'
    ARABIC = 'ar'
    PORTUGUESE = 'pt'
    BENGALI = 'bn'
    RUSSIAN = 'ru'
    JAPANESE = 'ja'
    GERMAN = 'de'
    FRENCH = 'fr'
    ITALIAN = 'it'
    KOREAN = 'ko'
    TURKISH = 'tr'
    VIETNAMESE = 'vi'
    THAI = 'th'
def get_language_codes() -> Dict[str, str]:
    """
    Get a dictionary of language names and their corresponding codes.
    
    Returns:
        Dict mapping language names to their ISO codes
    """
    return {
        # Most common languages first
        "English": "en",
        "Spanish": "es",
        "Mandarin Chinese": "zh",
        "Hindi": "hi",
        "Arabic": "ar",
        "Portuguese": "pt",
        "Bengali": "bn",
        "Russian": "ru",
        "Japanese": "ja",
        "German": "de",
        # Additional languages
        "French": "fr",
        "Italian": "it",
        "Korean": "ko",
        "Turkish": "tr",
        "Vietnamese": "vi",
        "Thai": "th"
    }

def get_language_name(code: str) -> str:
    """
    Get the full language name from its code.
    
    Args:
        code: ISO language code
        
    Returns:
        Full language name or 'Unknown' if code not found
    """
    language_dict = {v: k for k, v in get_language_codes().items()}
    return language_dict.get(code, "Unknown")

def get_language_code(name: str) -> str:
    """
    Get the language code from its full name.
    
    Args:
        name: Full language name
        
    Returns:
        ISO language code or 'en' if name not found
    """
    return get_language_codes().get(name, "en")

def get_supported_languages() -> List[str]:
    """
    Get list of supported language names.
    
    Returns:
        List of supported language names
    """
    return list(get_language_codes().keys())


# Set default language
CURRENT_LANGUAGE = SupportedLanguage.ENGLISH

def set_language(language: Union[str, SupportedLanguage]) -> None:
    """
    Set the current language for the application.
    
    Args:
        language: Language code or SupportedLanguage enum value
    """
    global CURRENT_LANGUAGE
    if isinstance(language, str):
        try:
            CURRENT_LANGUAGE = SupportedLanguage(language)
        except ValueError:
            logging.warning(f"Unsupported language: {language}. Falling back to English.")
            CURRENT_LANGUAGE = SupportedLanguage.ENGLISH
    else:
        CURRENT_LANGUAGE = language
    
    logging.info(f"Language set to: {CURRENT_LANGUAGE.value}")

def get_current_language() -> SupportedLanguage:
    """
    Get the current language setting.
    
    Returns:
        Current language as SupportedLanguage enum
    """
    return CURRENT_LANGUAGE

# Initialize logging with default language
logging.info(f"Logging system initialized with language: {CURRENT_LANGUAGE.value}")

class AdGenerator:
    """Ad text generator with TONIC compliance"""
    
    def __init__(self, api_key: str):
        """Initialize OpenAI client with API key validation"""
        if not api_key or not isinstance(api_key, str):
            raise ValueError("Valid OpenAI API key is required")
            
        try:
            import openai
            # Check for new OpenAI client version
            if hasattr(openai, 'OpenAI'):
                self.client = openai.OpenAI(api_key=api_key)
                self.is_legacy = False
            else:
                # Support legacy version
                openai.api_key = api_key
                self.client = openai
                self.is_legacy = True
                logging.warning("Using legacy OpenAI client")
        except ImportError:
            raise ImportError("OpenAI package not installed. Run: pip install openai")

    def generate_ad(self, product: str, language: str) -> Dict[str, str]:
        """Generate TONIC-compliant ad text with error handling"""
        try:
            # Validate inputs
            if not product or not language:
                raise ValueError("Product and language are required")

            system_message = """
            You are an expert ad copywriter who creates TONIC-compliant advertisements.
            Keep all titles in English but generate content in the specified language.
            
            Follow these rules strictly:
            1. NO superlatives (best, biggest, etc.)
            2. NO specific numbers or percentages
            3. NO brand names
            4. NO free offers or discounts
            5. NO guarantees or promises
            6. NO misleading claims
            7. NO public service references
            8. NO urgency phrases like "limited time"
            
            Use subjunctive mood (might, could, may) instead of definitive statements.
            """

            user_prompt = f"""
            Create engaging ad text for {product} in {language}.
            
            Required components:
            Headline:
            Primary Text:
            Striking Question:
            Bold Claim:
            How-To Hook:
            Emotional Trigger:
            Domain Name:
            """

            # Generate completion based on client version
            if self.is_legacy:
                response = self.client.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                generated_text = response.choices[0].message.content
            else:
                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                generated_text = response.choices[0].message.content

            # Parse response into components
            components = {}
            current_key: Optional[str] = None
            
            for line in generated_text.split('\n'):
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    current_key = key.strip()
                    components[current_key] = value.strip()
                elif current_key and line:
                    components[current_key] += ' ' + line

            return components

        except Exception as e:
            logging.error(f"Error generating ad text: {str(e)}")
            raise AdGenerationError(f"Failed to generate ad: {str(e)}")

def display_ad_component(title: str, content: str, index: int):
    """Display a single ad component with copy functionality"""
    st.markdown(f"#### {title}")
    
    # Content area with copy button
    col1, col2 = st.columns([5,1])
    
    with col1:
        # Use single line text input instead of text area
        st.text_input(
            "", 
            value=content,
            key=f"text_{index}",
            disabled=True,
            label_visibility="collapsed"
        )
    
    with col2:
        # Disable button if already copied
        button_disabled = st.session_state.get(f'copied_{index}', False)
        if st.button(
            "📋",
            key=f"copy_{index}",
            disabled=button_disabled,
            help="Copy to clipboard"
        ):
            st.session_state[f'copied_{index}'] = True
            st.toast(f"Copied {title}!", icon="✅")

def main():
    """Main application function with error handling and state management"""
    st.markdown("<h1 class='app-title'>Ad Text Generator</h1>", unsafe_allow_html=True)
    
    # Initialize session state
    if 'generated_ads' not in st.session_state:
        st.session_state.generated_ads = None
    if 'generating' not in st.session_state:
        st.session_state.generating = False

    # Load API key securely
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        api_key = st.text_input(
            "OpenAI API Key:",
            type="password",
            help="Enter your OpenAI API key. It will not be stored."
        )

    if not api_key:
        st.warning("Please enter your OpenAI API key")
        return

    try:
        generator = AdGenerator(api_key)
    except Exception as e:
        st.error(f"Failed to initialize generator: {str(e)}")
        return

    # Input fields
    with st.container():
        product = st.text_input(
            "Product/Service:",
            placeholder="Enter product name",
            key="product_input"
        )
        language = st.selectbox(
            "Language:",
            options=list(get_language_codes().keys()),
            key="language_select"
        )

    # Generate button with disable state
    generate_button = st.button(
        "Generate Ad",
        use_container_width=True,
        disabled=st.session_state.generating,
        key="generate_button"
    )

    if generate_button:
        if not product:
            st.warning("Please enter a product name")
            return

        try:
            st.session_state.generating = True
            with st.spinner("Creating..."):
                result = generator.generate_ad(product, language)
                st.session_state.generated_ads = result
        except Exception as e:
            st.error(f"Error: {str(e)}")
            logging.error(f"Generation failed: {str(e)}")
            return
        finally:
            st.session_state.generating = False

    # Display results
    if st.session_state.generated_ads:
        for i, (title, content) in enumerate(st.session_state.generated_ads.items()):
            display_ad_component(title, content, i)

        # Download button for results
        st.markdown("---")
        json_str = json.dumps(
            st.session_state.generated_ads,
            indent=2,
            ensure_ascii=False
        )
        st.download_button(
            "📥 Download JSON",
            data=json_str,
            file_name=f"ad_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True
        )

if __name__ == "__main__":
    main()