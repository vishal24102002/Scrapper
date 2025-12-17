import sqlite3
import subprocess
import hashlib
import os
from pathlib import Path

class GitHubPuller:
    def __init__(self, db_path='sqlite.db'):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize the database with password table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create table for storing hashed password
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auth_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _hash_password(self, password):
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def set_initial_password(self, password):
        """Set the password for the first time (can only be done once)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if password already exists
        cursor.execute('SELECT id FROM auth_config WHERE id = 1')
        if cursor.fetchone():
            conn.close()
            raise Exception("Password already set and cannot be changed!")
        
        # Insert hashed password
        hashed = self._hash_password(password)
        cursor.execute('INSERT INTO auth_config (id, password_hash) VALUES (1, ?)', 
                      (hashed,))
        conn.commit()
        conn.close()
        print("Password set successfully!")
    
    def _verify_password(self, password):
        """Verify the provided password against stored hash"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT password_hash FROM auth_config WHERE id = 1')
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            raise Exception("No password configured. Set initial password first.")
        
        stored_hash = result[0]
        provided_hash = self._hash_password(password)
        
        return stored_hash == provided_hash
    
    def pull_and_update(self, password, repo_path='.'):
        """
        Pull latest changes from GitHub repository
        
        Args:
            password (str): The authentication password
            repo_path (str): Path to the git repository (default: current directory)
        
        Returns:
            dict: Result of the operation with status and message
        """
        # Verify password
        if not self._verify_password(password):
            return {
                'success': False,
                'message': 'Authentication failed: Invalid password'
            }
        
        # Check if path exists and is a git repository
        repo_path = Path(repo_path).resolve()
        if not repo_path.exists():
            return {
                'success': False,
                'message': f'Repository path does not exist: {repo_path}'
            }
        
        git_dir = repo_path / '.git'
        if not git_dir.exists():
            return {
                'success': False,
                'message': f'Not a git repository: {repo_path}'
            }
        
        try:
            # Change to repository directory
            original_dir = os.getcwd()
            os.chdir(repo_path)
            
            # Fetch latest changes
            fetch_result = subprocess.run(
                ['git', 'fetch', 'origin'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if fetch_result.returncode != 0:
                return {
                    'success': False,
                    'message': f'Git fetch failed: {fetch_result.stderr}'
                }
            
            # Pull changes
            pull_result = subprocess.run(
                ['git', 'pull', 'origin','master'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            os.chdir(original_dir)
            
            if pull_result.returncode != 0:
                return {
                    'success': False,
                    'message': f'Git pull failed: {pull_result.stderr}'
                }
            
            return {
                'success': True,
                'message': 'Repository updated successfully',
                'output': pull_result.stdout
            }
            
        except subprocess.TimeoutExpired:
            os.chdir(original_dir)
            return {
                'success': False,
                'message': 'Git operation timed out'
            }
        except Exception as e:
            os.chdir(original_dir)
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }


# Example usage
if __name__ == '__main__':
    puller = GitHubPuller('sqlite.db')
    
    # First time setup - set password (can only be done once)
    try:
        puller.set_initial_password('your_secure_password_here')
    except Exception as e:
        print(f"Setup: {e}")
    
    # Pull and update code
    result = puller.pull_and_update(
        password='your_secure_password_here',
        repo_path='.'  # Current directory or specify path
    )
    
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")
    if result['success'] and 'output' in result:
        print(f"Output: {result['output']}")
