import logging
import jwt
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from passlib.context import CryptContext
import uuid

from app.models.user import UserCreate, UserInDB, User, TokenData
from app.config import settings

# Configuración de logger
logger = logging.getLogger("hydrous")

# Configuración de hashing para passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Base de datos en memoria para usuarios (temporal)
users_db: Dict[str, UserInDB] = {}


class AuthService:
    """Servicio para manejo de autenticación y autorización"""

    # Configuración de JWT
    SECRET_KEY = "temporalsecretkey123456789"  # Cambiar en producción y usar settings
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 horas

    def __init__(self):
        """Inicializador del servicio"""
        logger.info("Inicializando servicio de autenticación")

    def get_password_hash(self, password: str) -> str:
        """Genera hash seguro de contraseña"""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verifica si una contraseña coincide con el hash"""
        return pwd_context.verify(plain_password, hashed_password)

    def create_user(self, user_data: UserCreate) -> User:
        """Crea un nuevo usuario en el almacenamiento en memoria"""
        try:
            # Verificar si el correo ya existe
            for user in users_db.values():
                if user.email.lower() == user_data.email.lower():
                    logger.warning(
                        f"Intento de registro con email duplicado: {user_data.email}"
                    )
                    raise ValueError("Email ya registrado")

            # Crear usuario con hash de contraseña
            user_id = str(uuid.uuid4())
            db_user = UserInDB(
                id=user_id,
                password_hash=self.get_password_hash(user_data.password),
                email=user_data.email,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                company_name=user_data.company_name,
                location=user_data.location,
                sector=user_data.sector,
                subsector=user_data.subsector,
                created_at=datetime.utcnow(),
            )

            # Guardar en "base de datos" en memoria
            users_db[user_id] = db_user

            # Log para debug
            logger.info(f"Usuario creado: {user_id} - {user_data.email}")

            # Devolver versión pública (sin password_hash)
            return User(
                id=db_user.id,
                email=db_user.email,
                first_name=db_user.first_name,
                last_name=db_user.last_name,
                company_name=db_user.company_name,
                location=db_user.location,
                sector=db_user.sector,
                subsector=db_user.subsector,
                created_at=db_user.created_at,
            )
        except Exception as e:
            logger.error(f"Error creando usuario: {str(e)}")
            raise

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Autentica un usuario por email y contraseña"""
        try:
            # Buscar usuario por email
            user = None
            for db_user in users_db.values():
                if db_user.email.lower() == email.lower():
                    user = db_user
                    break

            if not user:
                logger.warning(f"Intento de login con email no encontrado: {email}")
                return None

            # Verificar contraseña
            if not self.verify_password(password, user.password_hash):
                logger.warning(f"Intento de login con contraseña incorrecta: {email}")
                return None

            # Devolver versión pública (sin password_hash)
            return User(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                company_name=user.company_name,
                location=user.location,
                sector=user.sector,
                subsector=user.subsector,
                created_at=user.created_at,
            )
        except Exception as e:
            logger.error(f"Error en autenticación: {str(e)}")
            return None

    def create_access_token(self, user_id: str) -> TokenData:
        """Crea un token JWT para el usuario"""
        try:
            # Configurar expiración
            expires_delta = timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)
            expires_at = datetime.utcnow() + expires_delta

            # Datos a codificar en el token
            to_encode = {"sub": user_id, "exp": expires_at}

            # Crear token
            encoded_jwt = jwt.encode(
                to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM
            )

            # Devolver datos del token
            return TokenData(
                access_token=encoded_jwt,
                token_type="bearer",
                user_id=user_id,
                expires_at=expires_at,
            )
        except Exception as e:
            logger.error(f"Error creando token: {str(e)}")
            raise

    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verifica y decodifica un token JWT"""
        try:
            # Decodificar token
            payload = jwt.decode(token, self.SECRET_KEY, algorithms=[self.ALGORITHM])
            user_id = payload.get("sub")

            if user_id is None:
                logger.warning("Token sin id de usuario")
                return None

            # Verificar si el usuario existe
            if user_id not in users_db:
                logger.warning(f"Token con id de usuario no existente: {user_id}")
                return None

            # Obtener datos del usuario
            user = users_db[user_id]

            # Devolver datos básicos del usuario (sin incluir password_hash)
            return {
                "id": user_id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "company_name": user.company_name,
                "location": user.location,
                "sector": user.sector,
                "subsector": user.subsector,
            }
        except jwt.ExpiredSignatureError:
            logger.warning("Token expirado")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Token inválido")
            return None
        except Exception as e:
            logger.error(f"Error verificando token: {str(e)}")
            return None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Obtiene un usuario por su ID"""
        try:
            db_user = users_db.get(user_id)
            if not db_user:
                return None

            # Devolver versión pública
            return User(
                id=db_user.id,
                email=db_user.email,
                first_name=db_user.first_name,
                last_name=db_user.last_name,
                company_name=db_user.company_name,
                location=db_user.location,
                sector=db_user.sector,
                subsector=db_user.subsector,
                created_at=db_user.created_at,
            )
        except Exception as e:
            logger.error(f"Error obteniendo usuario por ID: {str(e)}")
            return None


# Instancia global
auth_service = AuthService()
