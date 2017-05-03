import json

from flask import jsonify, request
from flask_swagger import swagger
from flask_jwt import jwt_required, current_identity

from .app import app
from .schemas import *
from .models import db, User, Analysis
from .tasks import save_analysis

__all__ = ['fva_analysis', 'sign_up', 'spec']


@app.route("/spec")
def spec():
    swag = swagger(app)
    swag['info']['version'] = "1.0"
    swag['info']['title'] = "Metabolitics API"
    return jsonify(swag)


@app.route('/analysis/fva', methods=['POST'])
@jwt_required()
def fva_analysis():
    """
    FVA analysis
    ---
    tags:
      - analysis
    parameters:
        -
          name: authorization
          in: header
          type: string
          required: true
        - in: body
          name: body
          schema:
            id: AnalysisInput
            required:
              - name
              - concentration_changes
            properties:
              name:
                  type: string
                  description: name of analysis
              concentration_changes:
                  type: object
                  description: concentration changes of metabolitics
    responses:
      200:
        description: Analysis info
      404:
        description: Analysis not found
      401:
        description: Analysis is not yours
    """
    (data, error) = AnalysisInputSchema().load(request.json)
    if error:
        return jsonify(error), 400
    analysis = Analysis(data['name'], current_identity)
    db.session.add(analysis)
    db.session.commit()
    analysis_id = analysis.id
    save_analysis.delay(analysis_id, data['concentration_changes'])
    return jsonify({'id': analysis_id})


@app.route('/analysis/list')
@jwt_required()
def user_analysis():
    """
    List of analysis of user
    ---
    tags:
        - analysis
    parameters:
        -
          name: authorization
          in: header
          type: string
          required: true
    """
    return AnalysisSchema(many=True).jsonify(
        i for i in current_identity.analysis)


@app.route('/analysis/detail/<id>')
@jwt_required()
def analysis_detail(id):
    """
    Get analysis detail from id
    ---
    tags:
      - analysis
    parameters:
        -
          name: authorization
          in: header
          type: string
          required: true
        -
          name: id
          in: path
          type: integer
          required: true
    responses:
      200:
        description: Analysis info
      404:
        description: Analysis not found
      401:
        description: Analysis is not yours
    """
    analysis = Analysis.query.get(id)
    if not analysis:
        return '', 404
    if analysis.user_id != current_identity.id:
        return '', 401
    if analysis.status:
        analysis.load_results()
    return AnalysisSchema().jsonify(analysis)


@app.route('/auth/sign-up', methods=['POST'])
def sign_up():
    """
    Create a new user
    ---
    tags:
      - users
    definitions:
      - schema:
          id: User
          required:
            - name
            - surname
            - email
            - affiliation
            - password
          properties:
            name:
                type: string
                description: name for user
            surname:
                type: string
                description: surname for user
            email:
                type: string
                description: email for user
            password:
                type: string
                description: password for user
            affiliation:
                type: string
                description: affiliation for user
    parameters:
      - in: body
        name: body
        schema:
            $ref: "#/definitions/User"
    responses:
      201:
        description: User created
    """
    (data, error) = UserSchema().load(request.json)
    if error:
        return jsonify(error), 400
    if User.query.filter_by(email=data.email).first():
        return jsonify({'email': ['this email in use']}), 400
    db.session.add(data)
    db.session.commit()
    return ''


@app.route('/auth/info')
@jwt_required()
def auth_info():
    """
    Get user info
    ---
    tags:
      - users
    parameters:
        -
          name: authorization
          in: header
          type: string
          required: true
    responses:
      200:
        description: User info
    """
    return UserSchema().jsonify(current_identity)


@app.route('/auth/update', methods=['POST'])
@jwt_required()
def auth_update():
    """
    Update user info
    ---
    tags:
      - users
    parameters:
      - in: body
        name: body
        schema:
            $ref: "#/definitions/User"
      -
        name: authorization
        in: header
        type: string
        required: true
    responses:
      200:
        description: User info
    """
    (data, error) = UserSchema(exclude=('password', )).load(request.json)
    if error:
        return jsonify(error), 400
    current_identity.name = data.name
    current_identity.surname = data.surname
    current_identity.email = data.email
    current_identity.affiliation = data.affiliation
    db.session.commit()
    return ''


@app.route('/auth/change-password', methods=['POST'])
@jwt_required()
def auth_change_password():
    """
    Change user password
    ---
    tags:
      - users
    parameters:
      - in: body
        name: body
        schema:
          id: ChangePassword
          required:
            - old_password
            - new_password
          properties:
            old_password:
                type: string
                description: old user password
            new_password:
                type: string
                description: new user password
      -
        name: authorization
        in: header
        type: string
        required: true
    responses:
      200:
        description: User info
    """
    (data, error) = PasswordChangeSchema().load(request.json)
    if error:
        return jsonify(error), 400
    if current_identity.password != data['old_password']:
        return '', 401
    current_identity.password = data['new_password']
    db.session.commit()
    return ''
