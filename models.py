# from flask_sqlalchemy import SQLAlchemy
# from datetime import datetime

# db = SQLAlchemy()


# class Log(db.Model):
#     __tablename__ = 'logs'
#     id = db.Column(db.Integer, primary_key=True)
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
#     type = db.Column(db.String(50))
#     message = db.Column(db.Text)
#     source = db.Column(db.String(100))


# class Command(db.Model):
#     __tablename__ = 'commands'
#     id = db.Column(db.Integer, primary_key=True)
#     command = db.Column(db.String(200))
#     status = db.Column(db.String(50))
#     response = db.Column(db.Text)
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# class Telemetry(db.Model):
#     __tablename__ = 'telemetry'
#     id = db.Column(db.Integer, primary_key=True)
#     key = db.Column(db.String(100))
#     value = db.Column(db.String(200))
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# class Image(db.Model):
#     __tablename__ = 'images'
#     id = db.Column(db.Integer, primary_key=True)
#     filename = db.Column(db.String(255))
#     url = db.Column(db.String(255))
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# ==========================================================
# MOIS
# ==========================================================

class Month(db.Model):

    __tablename__ = "months"

    id = db.Column(db.Integer, primary_key=True)

    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(20), nullable=False)

    # Relation avec les jours
    days = db.relationship(
        "Day",
        backref="month",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "year",
            "month",
            name="unique_year_month"
        ),
    )


# ==========================================================
# JOUR
# ==========================================================

class Day(db.Model):

    __tablename__ = "days"

    id = db.Column(db.Integer, primary_key=True)

    month_id = db.Column(
        db.Integer,
        db.ForeignKey("months.id"),
        nullable=False
    )

    date = db.Column(
        db.Date,
        nullable=False
    )

    # Relation avec les télémétries
    telemetry = db.relationship(
        "Telemetry",
        backref="day",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "month_id",
            "date",
            name="unique_month_day"
        ),
    )


# ==========================================================
# TELEMETRIE
# ==========================================================

class Telemetry(db.Model):

    __tablename__ = "telemetry"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    day_id = db.Column(
        db.Integer,
        db.ForeignKey("days.id"),
        nullable=False
    )

    key = db.Column(
        db.String(100),
        nullable=False
    )

    value = db.Column(
        db.String(100),
        nullable=False
    )

    timestamp = db.Column(
        db.DateTime,
        nullable=False,
        index=True
    )


# ==========================================================
# TES AUTRES MODELES
# ==========================================================

class Log(db.Model):

    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)

    message = db.Column(
        db.String(255),
        nullable=False
    )

    timestamp = db.Column(
        db.DateTime,
        default=datetime.now
    )


class Command(db.Model):

    __tablename__ = "commands"

    id = db.Column(db.Integer, primary_key=True)

    command = db.Column(
        db.String(100),
        nullable=False
    )

    timestamp = db.Column(
        db.DateTime,
        default=datetime.now
    )


class Image(db.Model):

    __tablename__ = "images"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    filename = db.Column(
        db.String(255),
        nullable=False
    )

    timestamp = db.Column(
        db.DateTime,
        default=datetime.now
    )