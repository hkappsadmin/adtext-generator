import os
import requests
from github import Github
import openai
from pathlib import Path
import base64
import re
from dotenv import load_dotenv
import tiktoken
from rich.console import Console 
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.text import Text
import time
import openai
import asyncio

class ConfigurationManager:
    """
    Manages configuration and environment variables
    """
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        
        # Required configurations
        self.required_vars = ['GITHUB_TOKEN', 'OPENAI_API_KEY']
        
        # Optional configurations with defaults
        self.defaults = {
            'MAX_TOKENS': 4000,
            'MAX_FILE_LINES': 300,
            'MAX_METHODS': 20,
            'MAX_METHOD_LINES': 50
        }
        
        self.config = {}
        self._load_configuration()

    def _load_configuration(self):
        """
        Load and validate configuration from environment variables
        """
        # Check required variables
        missing_vars = []
        for var in self.required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            self.config[var] = value

        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

        # Load optional variables with defaults
        for key, default_value in self.defaults.items():
            self.config[key] = int(os.getenv(key, default_value))

    def get(self, key):
        """
        Get configuration value
        """
        return self.config.get(key)

class LaravelCodeAnalyzer:
    def __init__(self, config_manager):
        """
        Initialize the analyzer with configuration
        """
        self.config = config_manager
        self.github_token = config_manager.get('GITHUB_TOKEN')
        self.g = Github(self.github_token)
        openai.api_key = config_manager.get('OPENAI_API_KEY')
        self.max_tokens = config_manager.get('MAX_TOKENS')
        self.encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        self.console = Console()  # Add this line
        
        # Define code complexity thresholds from configuration
        self.complexity_thresholds = {
            'lines': config_manager.get('MAX_FILE_LINES'),
            'methods': config_manager.get('MAX_METHODS'),
            'method_lines': config_manager.get('MAX_METHOD_LINES')
        }

        # Make sure you have these path configurations
        self.analysis_paths = {
            'app': ['.php'],
            'routes': ['.php'],
            'config': ['.php'],
            'database/migrations': ['.php'],
            'app/Http/Controllers': ['.php'],
            'app/Http/Middleware': ['.php'],
            'app/Models': ['.php'],
            'app/Services': ['.php'],
            'app/Providers': ['.php'],
        }
        
        self.ignore_paths = [
            'vendor/',
            'node_modules/',
            'storage/',
            'public/',
            'tests/',
            '.git/',
            'bootstrap/cache/',
            '.env',
            '*.min.js',
            '*.min.css',
            'package-lock.json',
            'composer.lock',
            'yarn.lock'
        ]

    def count_tokens(self, text):
        """
        Count the number of tokens in a text
        """
        return len(self.encoding.encode(text))

    def split_code_into_chunks(self, code, max_tokens):
        """
        Split code into chunks that fit within token limits
        """
        chunks = []
        lines = code.split('\n')
        current_chunk = []
        current_tokens = 0
        
        for line in lines:
            line_tokens = self.count_tokens(line + '\n')
            
            if current_tokens + line_tokens > max_tokens:
                # Save current chunk
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_tokens = line_tokens
            else:
                current_chunk.append(line)
                current_tokens += line_tokens
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        return chunks

    def analyze_repository(self, repo_url):
        """
        Analyze Laravel repository with progress tracking
        """
        self.console.print(Panel("[bold blue]Laravel Code Analysis Started[/bold blue]", 
                               subtitle="analyzing repository structure"))

        contents = self.get_repo_contents(repo_url)
        analysis_results = {}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        ) as progress:
            analyze_task = progress.add_task(
                "[cyan]Analyzing files...", 
                total=len(contents)
            )

            for file_info in contents:
                file_path = file_info['path']
                self.console.print(f"[yellow]→ Analyzing:[/yellow] {file_path}")
                
                analysis = self.analyze_laravel_code(file_info['content'], file_path)
                analysis_results[file_path] = analysis
                
                progress.advance(analyze_task)
                
                # Show quick summary of findings
                if "⚠️ Complexity Warnings" in analysis:
                    self.console.print(f"[red]⚠️  Issues found in {file_path}[/red]")
                else:
                    self.console.print(f"[green]✓ {file_path} analyzed[/green]")
                
                time.sleep(0.1)  # Small delay for better visual feedback

        # Print summary
        total_files = len(analysis_results)
        files_with_issues = sum(1 for a in analysis_results.values() if "⚠️ Complexity Warnings" in a)
        
        self.console.print("\n[bold]Analysis Summary:[/bold]")
        self.console.print(Panel(
            f"""
[cyan]Total Files Analyzed:[/cyan] {total_files}
[yellow]Files with Issues:[/yellow] {files_with_issues}
[green]Clean Files:[/green] {total_files - files_with_issues}
            """,
            title="Results",
            border_style="blue"
        ))

        return analysis_results
        
    def get_repo_contents(self, repo_url):
        """
        Get relevant Laravel files from a GitHub repository
        """
        try:
            # Extract owner and repo name from URL
            _, _, _, owner, repo_name = repo_url.rstrip('/').split('/')
            
            # Get repository
            repo = self.g.get_repo(f"{owner}/{repo_name}")
            
            # Get Laravel-specific contents
            contents = []
            for path in self.analysis_paths.keys():
                try:
                    self._get_contents_recursive(repo, path, contents)
                except Exception as e:
                    print(f"Warning: Could not access {path}: {str(e)}")
            
            return contents
        except Exception as e:
            print(f"Error fetching repository contents: {str(e)}")
            return []

    def _get_contents_recursive(self, repo, path, contents):
        """
        Recursively get Laravel files from repository
        """
        try:
            items = repo.get_contents(path)
            
            for item in items:
                if item.type == "dir":
                    self._get_contents_recursive(repo, item.path, contents)
                elif self.should_analyze_file(item.path):
                    contents.append({
                        'path': item.path,
                        'content': base64.b64decode(item.content).decode('utf-8')
                    })
        except Exception as e:
            print(f"Warning: Error accessing {path}: {str(e)}")

    def should_analyze_file(self, file_path):
        """
        Determine if a file should be analyzed based on path and extension
        """
        # Check if file is in ignored paths
        for ignore_path in self.ignore_paths:
            if ignore_path.endswith('/'):
                if file_path.startswith(ignore_path):
                    return False
            elif file_path.endswith(ignore_path) or ignore_path in file_path:
                return False

        # Check if file is in analysis paths
        for analysis_path, extensions in self.analysis_paths.items():
            if file_path.startswith(analysis_path):
                return any(file_path.endswith(ext) for ext in extensions)

        return False
    
    def analyze_code_complexity(self, code_content):
        """
        Analyze code complexity metrics
        """
        lines = code_content.split('\n')
        total_lines = len(lines)
        
        # Count methods
        method_pattern = r'function\s+\w+\s*\('
        methods = re.finditer(method_pattern, code_content)
        method_count = sum(1 for _ in methods)
        
        # Analyze method lengths
        method_blocks = re.split(method_pattern, code_content)
        long_methods = []
        
        for block in method_blocks[1:]:  # Skip first block (before first method)
            method_lines = len(block.split('\n'))
            if method_lines > self.complexity_thresholds['method_lines']:
                long_methods.append(method_lines)
        
        complexity_report = {
            'total_lines': total_lines,
            'method_count': method_count,
            'long_methods': len(long_methods),
            'exceeds_thresholds': {
                'file_too_long': total_lines > self.complexity_thresholds['lines'],
                'too_many_methods': method_count > self.complexity_thresholds['methods'],
                'has_long_methods': bool(long_methods)
            }
        }
        
        return complexity_report

    async def analyze_laravel_code_chunk(self, code_chunk, file_path, chunk_index, total_chunks):
        """
        Analyze a single chunk of Laravel code
        """
        try:
            file_type = self._get_laravel_file_type(file_path)
            
            chunk_context = f"This is chunk {chunk_index + 1} of {total_chunks} from the file."
            prompt = self._create_laravel_prompt(file_type, code_chunk, file_path, chunk_context)

            response = await asyncio.to_thread(openai.ChatCompletion.create,
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a Laravel expert performing code review. Focus on Laravel best practices, design patterns, and potential security issues."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000
            )
            
            return response.choices[0].message['content']
        except Exception as e:
            return f"Error analyzing code chunk: {str(e)}"

    def analyze_laravel_code(self, code_content, file_path):
        """
        Analyze Laravel code with chunking support
        """
        try:
            # First analyze complexity
            complexity_report = self.analyze_code_complexity(code_content)
            
            # Split code into chunks if necessary
            chunks = self.split_code_into_chunks(code_content, self.max_tokens // 2)
            
            # Analyze each chunk
            chunk_analyses = []
            for i, chunk in enumerate(chunks):
                # Run synchronously since we're in a sync method
                analysis = asyncio.run(self.analyze_laravel_code_chunk(chunk, file_path, i, len(chunks)))
                chunk_analyses.append(analysis)
            
            # Combine analyses
            combined_analysis = self._combine_analyses(chunk_analyses, complexity_report, file_path)
            return combined_analysis
        except Exception as e:
            return f"Error in analysis: {str(e)}"

    def _combine_analyses(self, chunk_analyses, complexity_report, file_path):
        """
        Combine multiple chunk analyses and complexity report into a single coherent analysis
        """
        combined = "# File Analysis Summary\n\n"
        
        # Add complexity warnings
        if any(complexity_report['exceeds_thresholds'].values()):
            combined += "## ⚠️ Complexity Warnings\n\n"
            if complexity_report['exceeds_thresholds']['file_too_long']:
                combined += f"- File is too long ({complexity_report['total_lines']} lines, recommended max: {self.complexity_thresholds['lines']})\n"
            if complexity_report['exceeds_thresholds']['too_many_methods']:
                combined += f"- Too many methods ({complexity_report['method_count']} methods, recommended max: {self.complexity_thresholds['methods']})\n"
            if complexity_report['exceeds_thresholds']['has_long_methods']:
                combined += f"- Contains {complexity_report['long_methods']} methods longer than {self.complexity_thresholds['method_lines']} lines\n"
            combined += "\n"
        
        # Add metrics
        combined += "## Metrics\n\n"
        combined += f"- Total Lines: {complexity_report['total_lines']}\n"
        combined += f"- Method Count: {complexity_report['method_count']}\n"
        combined += f"- Long Methods: {complexity_report['long_methods']}\n\n"
        
        # Combine chunk analyses
        if len(chunk_analyses) > 1:
            combined += "## Detailed Analysis\n\n"
            for i, analysis in enumerate(chunk_analyses, 1):
                combined += f"### Section {i}\n\n{analysis}\n\n"
        else:
            combined += "## Analysis\n\n" + chunk_analyses[0]
        
        return combined

    def _create_laravel_prompt(self, file_type, code_content, file_path, chunk_context=""):
        """
        Create a Laravel-specific analysis prompt based on file type
        """
        base_prompt = f"""Analyze the following Laravel {file_type} file ({file_path}).
        {chunk_context}
        
        Provide:
        1. Overview of the code's functionality
        2. Laravel best practices assessment
        3. Potential security vulnerabilities
        4. Performance considerations
        5. Suggested improvements
        
        Focus on Laravel-specific aspects such as:"""
        
        type_specific_prompts = {
            'Controller': """
            - RESTful practices
            - Route model binding
            - Form validation
            - Authorization
            - Response handling""",
            
            'Model': """
            - Eloquent relationships
            - Attributes and casting
            - Scopes and mutators
            - Mass assignment protection
            - Query optimization""",
            
            'Middleware': """
            - Request handling
            - Auth checks
            - Input sanitization
            - Response modification""",
            
            'Migration': """
            - Schema design
            - Indexes
            - Foreign keys
            - Rollback handling""",
            
            'Route': """
            - Organization
            - Middleware usage
            - Route naming
            - Model binding
            - API versioning"""
        }
        
        full_prompt = base_prompt + type_specific_prompts.get(file_type, "") + f"\n\nCode:\n{code_content}"
        return full_prompt

    def _get_laravel_file_type(self, file_path):
        """
        Determine the type of Laravel file based on its path
        """
        if 'Controllers' in file_path:
            return 'Controller'
        elif 'Models' in file_path:
            return 'Model'
        elif 'Middleware' in file_path:
            return 'Middleware'
        elif 'Providers' in file_path:
            return 'Service Provider'
        elif 'migrations' in file_path:
            return 'Migration'
        elif 'routes' in file_path:
            return 'Route'
        elif 'config' in file_path:
            return 'Config'
        return 'PHP'

    def _create_laravel_prompt(self, file_type, code_content, file_path, chunk_context=""):
        """
        Create a Laravel-specific analysis prompt based on file type
        """
        base_prompt = f"""Analyze the following Laravel {file_type} file ({file_path}).
        {chunk_context}
        
        Provide:
        1. Overview of the code's functionality
        2. Laravel best practices assessment
        3. Potential security vulnerabilities
        4. Performance considerations
        5. Suggested improvements
        
        Focus on Laravel-specific aspects such as:"""
        
        type_specific_prompts = {
            'Controller': """
            - RESTful practices
            - Route model binding
            - Form validation
            - Authorization
            - Response handling""",
            
            'Model': """
            - Eloquent relationships
            - Attributes and casting
            - Scopes and mutators
            - Mass assignment protection
            - Query optimization""",
            
            'Middleware': """
            - Request handling
            - Auth checks
            - Input sanitization
            - Response modification""",
            
            'Migration': """
            - Schema design
            - Indexes
            - Foreign keys
            - Rollback handling""",
            
            'Route': """
            - Organization
            - Middleware usage
            - Route naming
            - Model binding
            - API versioning"""
        }
        
        full_prompt = base_prompt + type_specific_prompts.get(file_type, "") + f"\n\nCode:\n{code_content}"
        return full_prompt

def save_analysis_to_file(analysis_results, output_path="laravel_analysis_report.md"):
    """
    Save analysis results to a markdown file with enhanced formatting
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Laravel Code Analysis Report\n\n")
        
        # Add summary section
        f.write("## Summary Statistics\n\n")
        total_files = len(analysis_results)
        complex_files = sum(1 for analysis in analysis_results.values() 
                          if "⚠️ Complexity Warnings" in analysis)
        
        f.write(f"- Total Files Analyzed: {total_files}\n")
        f.write(f"- Files with Complexity Warnings: {complex_files}\n\n")
        
        if complex_files > 0:
            f.write("### Files Needing Attention\n\n")
            for file_path, analysis in analysis_results.items():
                if "⚠️ Complexity Warnings" in analysis:
                    f.write(f"- {file_path}\n")
            f.write("\n")
        
        # Group files by type
        grouped_results = {}
        for file_path, analysis in analysis_results.items():
            file_type = file_path.split('/')[1] if '/' in file_path else 'Other'
            if file_type not in grouped_results:
                grouped_results[file_type] = {}
            grouped_results[file_type][file_path] = analysis
        
        # Write detailed analysis
        for file_type, files in grouped_results.items():
            f.write(f"## {file_type}\n\n")
            for file_path, analysis in files.items():
                f.write(f"### {file_path}\n\n")
                f.write(analysis)
                f.write("\n\n---\n\n")

def create_default_env():
    """
    Create a default .env file if it doesn't exist
    """
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write("""# Laravel Code Analyzer Configuration
GITHUB_TOKEN=your_github_token_here
OPENAI_API_KEY=your_openai_api_key_here

# Analysis Configuration
MAX_TOKENS=4000
MAX_FILE_LINES=300
MAX_METHODS=20
MAX_METHOD_LINES=50
""")
        print("Created default .env file. Please update it with your tokens.")
        return False
    return True



def main():
    # Create default .env if it doesn't exist
    if not create_default_env():
        return

    try:

        st.title("Ad Text Generator")
    
        # Language selector
        selected_language = st.selectbox(
            "Select Language",
            options=get_supported_languages(),
            index=0  # Default to first language (English)
        )
        
        # Set the application language
        current_lang_code = get_language_code(selected_language)
        set_language(current_lang_code)
        
        # Log language selection
        logging.info(f"Selected language: {selected_language} ({current_lang_code})")
        # Initialize configuration
        config_manager = ConfigurationManager()
        
        # Initialize analyzer
        analyzer = LaravelCodeAnalyzer(config_manager)
        
        # Get repository URL from user
        repo_url = input("Enter Laravel GitHub repository URL: ")
        
        # Analyze repository
        print("Starting Laravel repository analysis...")
        print(f"Using configuration:")
        print(f"- Max file lines: {config_manager.get('MAX_FILE_LINES')}")
        print(f"- Max methods per class: {config_manager.get('MAX_METHODS')}")
        print(f"- Max lines per method: {config_manager.get('MAX_METHOD_LINES')}")
        
        analysis_results = analyzer.analyze_repository(repo_url)
        
        # Save results
        output_file = "laravel_analysis_report.md"
        save_analysis_to_file(analysis_results, output_file)
        print(f"Analysis completed! Results saved to {output_file}")
        
    except ValueError as e:
        print(f"Configuration Error: {str(e)}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()