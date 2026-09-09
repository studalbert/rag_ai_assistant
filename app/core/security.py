from passlib.context import CryptContext

# schemes=["argon2"] — используем только Argon2, deprecated="auto" автоматически
# пометит старые хэши как устаревшие, если когда-нибудь добавишь ещё одну схему в список
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
