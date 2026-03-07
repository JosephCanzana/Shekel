from app.extensions import db


class BaseModel(db.Model):
    # Abstract magic method that says to sql that this is not mapped in database tables
    __abstract__ = True

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
            return self
        except Exception as e:
            db.session.rollback()
            raise e

    def delete(self):
        try:
            db.session.delete(self)
            db.session.commit()
            return self
        except Exception as e:
            db.session.rollback()
            raise e

    @classmethod
    def get_by_id(cls, id):
        return cls.query.get(id)

    @classmethod
    def get_all(cls):
        return cls.query.all()
