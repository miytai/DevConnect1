from flask import Flask, render_template, request, jsonify, abort
from config import Config
from database import db, Product, Promotion
import os

app = Flask(__name__)
app.config.from_object(Config)

# Инициализация базы данных
db.init_app(app)

# Создаем папки если их нет
os.makedirs(os.path.join(app.static_folder, 'css'), exist_ok=True)
os.makedirs(os.path.join(app.static_folder, 'js'), exist_ok=True)
os.makedirs(os.path.join(app.static_folder, 'images', 'teas'), exist_ok=True)
os.makedirs('templates', exist_ok=True)

@app.route('/')
def index():
    # Получаем популярные товары для главной страницы
    popular_products = Product.query.filter_by(is_active=True).limit(6).all()
    promotions = Promotion.query.filter_by(is_active=True).all()
    return render_template('index.html', 
                         products=popular_products,
                         promotions=promotions)

@app.route('/catalog')
def catalog():
    category = request.args.get('category', 'all')
    
    if category == 'all':
        products = Product.query.filter_by(is_active=True).all()
    else:
        products = Product.query.filter_by(
            is_active=True, 
            category=category
        ).all()
    
    # Получаем все уникальные категории
    categories = db.session.query(Product.category).distinct().all()
    categories = [cat[0] for cat in categories]
    
    return render_template('catalog.html', 
                         products=products,
                         categories=categories,
                         current_category=category)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_active:
        abort(404)
    
    # Получаем похожие товары
    similar_products = Product.query.filter(
        Product.category == product.category,
        Product.id != product.id,
        Product.is_active == True
    ).limit(4).all()
    
    return render_template('product.html', 
                         product=product,
                         similar_products=similar_products)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/promotions')
def promotions():
    active_promotions = Promotion.query.filter_by(is_active=True).all()
    return render_template('promotions.html', promotions=active_promotions)

@app.route('/api/products')
def api_products():
    products = Product.query.filter_by(is_active=True).all()
    return jsonify([product.to_dict() for product in products])

@app.route('/api/products/<int:product_id>')
def api_product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_active:
        abort(404)
    return jsonify(product.to_dict())

if __name__ == '__main__':
    app.run(debug=True, port=5000)