from typing import Callable

import arcade
from pyglet.event import EVENT_HANDLE_STATE
from random import randint, uniform, choice

from arcade.gui import UIManager, UITextureButton, UIMessageBox, UIImage, UILabel
from arcade.gui.widgets.layout import UIAnchorLayout, UIBoxLayout
from arcade.particles import Emitter, EmitBurst, EmitMaintainCount, FadeParticle

from pyglet.graphics import Batch

import sqlite3
import os

GRAVITY = 1
COYOTE_TIME = 0.08
JUMP_SPEED = 24
JUMP_BUFFER = 0.12

SPARK_TEX = [
    arcade.make_soft_circle_texture(8, arcade.color.PASTEL_YELLOW),
    arcade.make_soft_circle_texture(8, arcade.color.BLUEBERRY),
    arcade.make_soft_circle_texture(8, arcade.color.BABY_BLUE),
    arcade.make_soft_circle_texture(8, arcade.color.ELECTRIC_CRIMSON),
]


def gravity_drag(p):  # Для искр: чуть вниз и затухание скорости
    p.change_y += -0.03
    p.change_x *= 0.92
    p.change_y *= 0.92


def make_explosion(x, y, count=80):
    return Emitter(
        center_xy=(x, y),
        emit_controller=EmitBurst(count),
        particle_factory=lambda e: FadeParticle(
            filename_or_texture=choice(SPARK_TEX),
            change_xy=arcade.math.rand_in_circle((0.0, 0.0), 8.0),
            lifetime=uniform(0.6, 1.0),
            start_alpha=255, end_alpha=0,
            scale=uniform(0.4, 0.6),
            mutation_callback=gravity_drag,
        ),
    )


def make_trail(attached_sprite, maintain=60):
    """След за пулей"""
    emit = Emitter(
        center_xy=(attached_sprite.center_x, attached_sprite.center_y),
        emit_controller=EmitMaintainCount(maintain),
        particle_factory=lambda e: FadeParticle(
            filename_or_texture=choice(SPARK_TEX),
            change_xy=arcade.math.rand_in_circle((0.0, 0.0), 1.6),
            lifetime=uniform(0.3, 0.6),
            start_alpha=220, end_alpha=0,
            scale=uniform(0.2, 0.4),
        ),
    )
    # Хитрость: каждое обновление будем прижимать центр к спрайту (см. ниже)
    emit._attached = attached_sprite
    return emit


class DamageNumber(arcade.Sprite):
    """Летящая цифра над врагом для визуализации урона"""
    def __init__(self, center_x, center_y, cur_damage: int):
        super().__init__()
        self.texture = arcade.load_texture(f"assets/damage_number_{cur_damage}.png")

        self.center_x = center_x
        self.center_y = center_y

        self.life_time = 1 # урон над врагом будет показан только на секунду

    def update(self, delta_time: float = 1 / 60, *args, **kwargs) -> None:
        self.life_time -= delta_time
        if self.life_time <= 0:
            self.remove_from_sprite_lists()
        self.center_y += 30 * delta_time
        self.alpha -= 2.6 # примерно через секунду прозрачность станет 0


class Enemy(arcade.Sprite):
    def __init__(self, level_num):
        super().__init__()
        monster_type = randint(1, 3)
        base_texture = arcade.load_texture(f"assets/monsters/monster_{monster_type}.png")
        self.texture = base_texture.flip_horizontally() # сначала врага смотрит влево
        self.defeated_texture = arcade.load_texture(f"assets/monsters/defeated_monster_{monster_type}.png")

        if level_num == 1:
            self.center_x = 1216
        else:
            self.center_x = 2350

        if level_num != 3:
            self.center_y = 162
        else:
            self.center_y = 14 * 64 + self.height / 2

        self.change_x = randint(70, 110)
        self.direction = -1 # -1 или 1 (влево или вправо)

        self.change_direction = False # поменял ли враг свое направление
        self.stop_timer = uniform(0.5, 0.8) # время замирания врага

        self.enemy_damage_sound = arcade.load_sound("assets/sounds/Звук удара игрока по врагу.mp3")
        self.enemy_death_sound = arcade.load_sound("assets/sounds/Звук убийства врага.mp3")

        self.health = randint(9, 17) # от 2 до 5 ударов

        self.is_hitted = False # Если во врага попали
        self.is_defeated = False # Если враг умер
        self.hit_timer = 0.1 # Анимация попадания во врага только на 100 мс

        self.can_attack = True # Может ли враг ударить
        self.reload_timer = 2

    def update(self, delta_time: float, player_x: int) -> None:
        # Если текущее направление не совпадает с предыдущим
        if (player_x - self.center_x) // abs(player_x - self.center_x) != self.direction:
            self.direction *= -1 # меняем направление
            self.texture = self.texture.flip_horizontally()
            self.change_direction = True

        # Если враг поменял направление - заставляем его замереть
        if self.change_direction:
            self.stop_timer -= delta_time
            if self.stop_timer <= 0:
                self.change_direction = False
                self.stop_timer = uniform(0.5, 0.8)
        else:
            self.center_x += self.change_x * self.direction * delta_time

        if self.is_hitted:
            self.hit_timer -= delta_time
            if self.hit_timer < 0:
                if self.is_defeated:
                    self.remove_from_sprite_lists() # Если убили - удаляем спрайт
                else:
                    self.color = (255, 255, 255) # возвращаем обычные каналы
                self.hit_timer = 0.1

        # Если врага не может атаковать - значит он уже ударил
        if not self.can_attack:
            # Ждём пока он перезарядится
            self.reload_timer -= delta_time
            if self.reload_timer <= 0:
                self.can_attack = True
                self.reload_timer = 2

    def process_bullet_hit(self, cur_damage: int):
        """обрабатываем попадание пули во врага"""
        self.is_hitted = True

        self.health -= cur_damage
        self.is_defeated = self.health <= 0
        if self.is_defeated:
            self.enemy_damage_sound.play()
            self.texture = self.defeated_texture
        else:
            self.enemy_death_sound.play()
            # Оставляем только красный канал
            self.color = (255, 128, 128)

    def reload(self):
        self.can_attack = False


class Bullet(arcade.Sprite):
    def __init__(self, center_x: float, center_y: float, direction: int):
        super().__init__()
        self.texture = arcade.load_texture("assets/magic_bullet.png")
        # В зависимости от направления меняем текстуру
        if direction == -1:
            self.texture = self.texture.flip_horizontally()

        self.scale = 0.4

        self.change_x = 180
        self.direction = direction # Пуля летит по направлению взгляда

        self.center_x = center_x
        self.center_y = center_y

    def update(self, delta_time: float = 1 / 60, *args, **kwargs) -> None:
        self.center_x += self.change_x * self.direction * delta_time
        # Если пуля каким-то образом вышла за пределы карты - удаляем её
        if self.center_x + self.width / 2 <= 0 or self.center_x - self.width / 2 >= 50 * 64:
            self.remove_from_sprite_lists()


class Player(arcade.Sprite):
    def __init__(self, user_id):
        super().__init__()
        # Начальная текстура - герой смотрит влево
        self.base_textures = {-1: arcade.load_texture("assets/player/left_player.png"),
                              1: arcade.load_texture("assets/player/right_player.png")}
        self.attacking_textures = {-1: arcade.load_texture("assets/player/left_attack.png"),
                                   1: arcade.load_texture("assets/player/right_attack.png")}
        self.jumping_textures = {-1: arcade.load_texture("assets/player/left_jump.png"),
                                 1: arcade.load_texture("assets/player/right_jump.png")}

        self.texture = self.base_textures[1]
        self.direction = 1 # текущее направление - направо

        self.attack_sound = arcade.load_sound("assets/sounds/Звук всплеска магии (mp3cut.net).mp3")
        self.dash_sound = arcade.load_sound("assets/sounds/Звук рывка.mp3")
        self.player_hitted_sound = arcade.load_sound("assets/sounds/Звук удара врага по игроку.mp3")

        # Начальная позиция
        self.center_x = 250
        self.center_y = 200

        # Хитбоксы ног и тела для более точной обработки столкновений
        self.feet_hitbox = arcade.LBWH(self.left + 20, self.bottom - 5, 41, 6)
        self.body_hitbox = arcade.LBWH(self.left + 21, self.bottom + 1, 34, 80)

        con = sqlite3.connect("player.db")
        cursor = con.cursor()
        # Подгружаем характеристики героя из базы данных
        player_data = cursor.execute("SELECT * FROM players WHERE id = ?", (user_id, )).fetchone()
        health_num, damage_num, self.reload_num = player_data[1:4]

        # значения на нулевом и 1, 2, 3 уровни
        health_levels = [5, 8, 12, 15]
        damage_levels = [(4, 5), (5, 5), (5, 6), (6, 7)]
        self.reload_levels = [3, 2.5, 2, 1] # сохраняем в атрибуте класса, чтобы потом обратится

        self.health = health_levels[health_num]
        self.is_hitted = False # Если враг ударил игрока
        self.hit_timer = 0.1
        self.damage = damage_levels[damage_num] # количество урона, которое наносит герой

        self.speed = 150
        self.durability = 10 # выносливость
        self.is_jump = False
        self.is_climbing = False # забирается ли игрок по лестнице

        self.is_dash = False # Сделал ли игрок рывок
        self.dash_speed = 30 # Начальная скорость рывка
        self.boost = 4.5 # Ускорение

        self.is_attacking = False # Свойство для проверки атакует ли герой
        self.attack_duration = 0.3 # Длительность анимации атаки

        self.is_reload = False
        self.is_fired = False # Стрельнул ли игрок
        self.shot_count = 0 # количество выстрелов
        self.time_since_shot = 0 # Время спустя выстрел
        self.reload_duration = self.reload_levels[self.reload_num] # Время, затрачиваемое на перезарядку


        # Таймер на анимацию бездейсвтия: 4 секунды
        self.staying_duration = 4
        # Текстуры (кадры) для анимации
        self.staying_textures = {-1: [], 1: []}
        for i in range(1, 5):
            left_texture = arcade.load_texture(f"assets/player_freeze_animation/left/animation-{i}.png.png")
            self.staying_textures[-1].append(left_texture)

            right_texture = arcade.load_texture(f"assets/player_freeze_animation/right/image-{i}.png.png")
            self.staying_textures[1].append(right_texture)

        self.cur_freeze_frame = 0 # Текущий кадр - персонаж смотрит влево

        self.walk_animation_timer = 0.1
        self.cur_walk_frame = 0
        self.walk_frames = {-1: [], 1: []}
        for i in range(1, 10):
            left_texture = arcade.load_texture(f"assets/player_walk_animation/left/animation-{i}.png.png")
            self.walk_frames[-1].append(left_texture)

            right_texture = arcade.load_texture(f"assets/player_walk_animation/right/animation_{i}.png")
            self.walk_frames[1].append(right_texture)

    def update(self, delta_time, pressed_keys) -> None:
        # Передвижение героя
        self.update_movement(delta_time, pressed_keys)

        if self.is_attacking:
            # Если персонаж атаковал, увеличиваем время ожидания анимации до 4 секунд
            self.staying_duration = 4
            # Анимация атаки
            self.attack_duration -= delta_time
            if self.attack_duration <= 0:
                self.is_attacking = False
                self.attack_duration = 0.3
                self.change_jump_texture() # меняем текстуру на прежнюю

        self.update_shooting_timer(delta_time)
        self.do_reload(delta_time)

        if self.is_dash:
            # Если игрок сделал рывок
            self.center_x += self.dash_speed # передвигаем игрока
            self.dash_speed -= self.boost # уменьшаем начальную скорость
            if self.dash_speed * self.direction <= 0:
                self.is_dash = False

        if self.is_hitted:
            self.hit_timer -= delta_time
            if self.hit_timer < 0:
                self.hit_timer = 0.1
                self.color = (255, 255, 255)
                self.is_hitted = False

        self.update_durability()

    def update_movement(self, delta_time: float, pressed_keys: set):
        """Передвижение героя"""
        dx, dy = 0, 0
        if arcade.key.A in pressed_keys:
            # Если было право - меняем на лево (один раз)
            if self.direction == 1:
                self.direction = -1
                # Текстуру меняем только когда игрок не на лестнице
                if not self.is_climbing:
                    self.texture = self.base_textures[-1] # Меняем на левую текстуру
                    self.sync_hit_box_to_texture() # Меняем хитбокс в зависимости от текущей текстуры

            dx = -self.speed * delta_time
        if arcade.key.D in pressed_keys:
            # Если было лево - меняем на право (один раз)
            if self.direction == -1:
                self.direction = 1
                # Текстуру меняем только когда игрок не на лестнице
                if not self.is_climbing:
                    self.texture = self.base_textures[1] # меняем на правую текстуру
                    self.sync_hit_box_to_texture() # Меняем хитбокс в зависимости от текущей текстуры

            dx = self.speed * delta_time
        if arcade.key.W in pressed_keys or arcade.key.S in pressed_keys:
            # Если игрок двигался вверх или вниз - фиксируем это
            dy = self.change_y

        if dx == 0 and dy == 0:
            # Если персонаж вообще не двигается - начинаем анимацию бездействия
            self.staying_duration -= delta_time
            if self.staying_duration <= 0:
                self.staying_duration = 0.2 # Смена кадра каждые 200 мс
                self.cur_freeze_frame = (self.cur_freeze_frame + 1) % 4
                # В зависимости от направления устанавливаем текстуру
                self.texture = self.staying_textures[self.direction][self.cur_freeze_frame]
        else:
            # Если персонаж двинулся - сбрасываем текстуру на начальную
            if self.cur_freeze_frame != 0:
                self.cur_freeze_frame = 0
                self.texture = self.base_textures[self.direction]

            # Если персонаж двигался, то увеличиваем время ожидания анимации до 4 секунд
            self.staying_duration = 4

        # Проверяем находится ли игрок в состоянии ходьбы
        if not self.is_jump and not self.is_climbing:
            if dx != 0:
                # Начинаем аниамцию ходьбы (9 кадров, 0.1 мс на один кадр)
                self.walk_animation_timer -= delta_time
                if self.walk_animation_timer <= 0:
                    self.cur_walk_frame = (self.cur_walk_frame + 1) % 9
                    self.texture = self.walk_frames[self.direction][self.cur_walk_frame]
                    self.walk_animation_timer = 0.1
            else:
                # Если персонаж остановился - меняем текстуру на начальную
                if self.cur_walk_frame != 0:
                    self.cur_walk_frame = 0
                    self.texture = self.base_textures[self.direction]

        self.center_x += dx

        # Обновляем хитбоксы каждый кадр
        self.feet_hitbox = arcade.LBWH(self.left + 20, self.bottom - 2, 41, 4)
        self.body_hitbox = arcade.LBWH(self.left + 21, self.bottom + 4, 34, 80)

    def attack(self, create_bullet_callback: Callable):
        # Если игрок перезаряжается - атаковать нельзя
        if self.is_reload:
            return

        self.player_sound = self.attack_sound.play() # сохраняем объект звука, чтобы в нужный момент могли отключить

        self.is_attacking = True
        self.is_fired = True
        self.shot_count += 1
        self.texture = self.attacking_textures[self.direction] # Меняем текстуру на атакующую

        create_bullet_callback(self.center_x + 60 * self.direction, self.center_y, self.direction)

    def process_hit(self):
        self.is_hitted = True
        self.health -= 1

        self.player_hitted_sound.play()

        self.color = (255, 128, 128)

    def make_dash(self):
        # Если выносливости не хватает - рывок сделать нельзя
        if self.durability < 5.5:
            return

        self.dash_sound.play()
        self.is_dash = True
        # Устанавливаем начальные параметры
        self.dash_speed = 30 * self.direction
        self.boost = 4.5 * self.direction

        # Уменьшаем выносливость после рывка
        self.durability -= 5.5
        # При рывке также увеличиваем время ожидания анимации до 4 секунд
        self.staying_duration = 4
        # Если мы прервали анимацию бездействия - возвращаем первый кадр
        if self.cur_freeze_frame == 1:
            self.cur_freeze_frame = 0
            self.texture = self.base_textures[self.direction]

    def do_reload(self, dt: float):
        if self.is_reload:
            self.reload_duration -= dt
            if self.reload_duration <= 0:
                # возвращаем прошлое время перезарядки
                self.reload_duration = self.reload_levels[self.reload_num]
                self.is_reload = False

    def update_shooting_timer(self, dt):
        if self.is_fired:
            # Если игрок выстрелил - фиксируем время после выстрела
            self.time_since_shot += dt
            if self.time_since_shot >= 0.5:
                # Если за 500 мс после первого выстрела было сделано еще
                # три и более выстрела, то оружие перегорело - начинаем перезарядку
                if self.shot_count >= 3:
                    self.is_reload = True

                # В любом случае сбрасываем параметры
                self.is_fired = False
                self.time_since_shot = 0
                self.shot_count = 0

    def update_durability(self):
        # увеличиваем выносливость каждый кадр
        self.durability = min(10.0, self.durability + 0.1)

    def change_jump_texture(self):
        # В зависимости от текущего состояния героя - меняем его текстуры
        if self.is_attacking:
            self.texture = self.attacking_textures[self.direction]
        elif self.is_jump:
            self.texture = self.jumping_textures[self.direction]
        elif self.is_climbing:
            self.texture = arcade.load_texture("assets/player/climbing.png")
        else:
            self.texture = self.base_textures[self.direction]


class BetterPhysicEngine:
    """Класс для улучшенной проверки коллизий, которые основан на более точных хитбоксах игрока"""
    def __init__(self, player: Player, walls: arcade.SpriteList, platforms: arcade.SpriteList,
                 ladders_top: arcade.SpriteList, ladders: arcade.SpriteList, finish: arcade.SpriteList):
        self.player = player
        self.target_sprites = walls
        self.platforms = platforms
        self.ladders_top = ladders_top
        self.ladders = ladders
        self.finish = finish

    def can_jump(self):
        walls = arcade.get_sprites_in_rect(self.player.feet_hitbox, self.target_sprites)
        platforms = arcade.get_sprites_in_rect(self.player.feet_hitbox, self.platforms)
        return len(walls) > 0 or len(platforms) > 0

    def is_on_ladder_top(self):
        top = arcade.get_sprites_in_rect(self.player.feet_hitbox, self.ladders_top)
        return top

    def is_on_ladder(self):
        ladders = arcade.get_sprites_in_rect(self.player.body_hitbox, self.ladders)
        return len(ladders) > 0

    def is_on_finish(self):
        finish = arcade.get_sprites_in_rect(self.player.feet_hitbox, self.finish)
        return len(finish) > 0


class MyGame(arcade.View):
    def __init__(self, level_num, user_id):
        super().__init__()
        self.user_id = user_id # id игрока
        self.level_num = level_num # номер уровня, на котором хочет играть пользователь

        self.tile_map = arcade.load_tilemap(f"test_{level_num}.tmx") # загружаем карту по уровню
        self.scene = arcade.Scene.from_tilemap(self.tile_map)
        arcade.set_background_color(arcade.color.BLUE_SAPPHIRE)

        self.world_width = 80 * 64 # Ширина карты, кол-во тайлов * ширину тайла
        self.world_height = 20 * 64 # Высота карты

        self.emitters = []
        self.trails = {}

        # Изначально спаун врагов отключен
        self.is_enemies_spawn = False
        # номер тайла, после которого начнется спаун врагов на каждом уровне
        self.spawn_distanation = [7, 14, 14]

        self.coins_list = self.scene["coins"]
        self.finish_list = self.scene["finish"]

        self.coin_catching_sound = arcade.load_sound("assets/sounds/Звук подбора монет.mp3")
        self.jump_sound = arcade.load_sound("assets/sounds/Звук прыжка.mp3")
        self.start_climbing_sound = arcade.load_sound("assets/sounds/Звук карабканья по листьям.mp3")
        self.bullet_miss_sound = arcade.load_sound("assets/sounds/Звук столкновения пули со стеной.mp3")
        self.win_sound = arcade.load_sound("assets/sounds/Победный звук.mp3")
        self.game_over_sound = arcade.load_sound("assets/sounds/Звук во время проигрыша.mp3")

        self.walls = self.scene["collisions"]
        self.platforms = arcade.SpriteList()

        plat = arcade.Sprite("assets/platform.png")
        if level_num == 1:
            plat.left = 200
        elif level_num == 2:
            plat.left = 2300
        else:
            plat.left = -1000
        plat.bottom = 252
        plat.boundary_top = 600
        plat.boundary_bottom = 252
        plat.change_y = 2
        self.platforms.append(plat)

        self.ladders_top = self.scene["ladder_top"]
        self.last_top = [] # Список для хранения верхушек лестниц
        self.move_down = False # Хочет ли игрок идти вниз

        self.world_camera = arcade.camera.Camera2D()
        self.last_y = 0 # Последняя координата y, на которой остановилась камера
        self.gui_camera = arcade.camera.Camera2D()

    def setup(self):
        self.player = Player(self.user_id) # Создаем объект игрока
        self.player_list = arcade.SpriteList()
        self.player_list.append(self.player)

        self.player_is_jump = False
        self.jump_buffer_time = 0 # Буфферное время прыжка
        self.time_since_grounded = 1000.0 # Время с начала прыжка

        self.bullets_list = arcade.SpriteList()
        self.enemies_list = arcade.SpriteList()
        self.damage_numbers_list = arcade.SpriteList()

        # Добавляем иконку настроек
        setting = arcade.Sprite("assets/settings_icon.png", 1.0, self.width - 32, self.height - 32)
        self.settings = arcade.SpriteList()
        self.settings.append(setting)

        self.pressed_keys = set() # Для хранения нажатых кнопок


        self.engine = arcade.PhysicsEnginePlatformer(player_sprite=self.player, gravity_constant=GRAVITY, walls=self.walls, platforms=self.platforms)
        self.better_engine = BetterPhysicEngine(self.player, self.walls, self.platforms, self.ladders_top, self.scene["ladders"], self.finish_list)

        self.batch = Batch()
        self.coins_count = 0 # Количество заработанных монет во время игры
        self.kills_count = 0 # Количество убийств врага во время игры
        self.text_score = arcade.Text("Монеты: 0", 250, self.height - 20, arcade.color.WHITE, 24, anchor_x="left", anchor_y="top", batch=self.batch)
        self.health_text = arcade.Text(f"Здоровье: {self.player.health}", 20, self.height - 20,
                                       arcade.color.WHITE, 24, anchor_x="left", anchor_y="top", batch=self.batch)

    def on_draw(self) -> EVENT_HANDLE_STATE:
        self.clear()

        self.world_camera.use()

        self.scene.draw()
        self.player_list.draw()
        self.bullets_list.draw()
        self.enemies_list.draw()
        self.platforms.draw()
        self.damage_numbers_list.draw()

        for e in self.emitters:
            e.draw()

        self.gui_camera.use()

        self.settings.draw()
        self.batch.draw()

    def on_update(self, delta_time: float) -> bool | None:
        self.player.update(delta_time, self.pressed_keys)

        for bullet in self.bullets_list:
            # Передвигаем пулю
            bullet.update()
            # Проверяем столкновение пули со всеми врагами
            killed_enemies = arcade.check_for_collision_with_list(bullet, self.enemies_list)
            for enemy in killed_enemies:
                # Выбираем случайный урон игрока в пределах его уровня
                cur_damage = randint(self.player.damage[0], self.player.damage[1])
                # Визуализация урона: создаем частицы разового залпа
                self.emitters.append(make_explosion(enemy.center_x, enemy.center_y))
                # Наносим урон врагу
                enemy.process_bullet_hit(cur_damage)

                # Если убили врага
                if enemy.health <= 0:
                    self.kills_count += 1
                    # Начисляем две монеты за убийство врага
                    self.coins_count += 2
                    self.text_score.text = f"Монеты: {self.coins_count}"
                    cur_damage = 3 # Если враг убит - ставим другой знак

                # Создаем спрайт - нанесенный урон игрока для визуального восприятия
                number = DamageNumber(enemy.center_x + enemy.width / 2, enemy.center_y + enemy.height / 2, cur_damage)
                self.damage_numbers_list.append(number)

                # Не забываем остановить частицу за пулей
                self.emitters.remove(self.trails[bullet])

                # Удаляем пулю
                bullet.remove_from_sprite_lists()

            # Проверяем столкновение пули со стенами
            missed_bullets = arcade.check_for_collision_with_list(bullet, self.walls)
            if missed_bullets:
                # Останавливаем звук выстрела и включаем звук промаха
                arcade.stop_sound(self.player.player_sound)
                self.bullet_miss_sound.play()
                # Не забываем остановить частицу за пулей
                self.emitters.remove(self.trails[bullet])
                # В конце удаляем спрайт пули из списка
                bullet.remove_from_sprite_lists()

        # Проверяем столкновение игрока с врагами
        enemies = arcade.check_for_collision_with_list(self.player, self.enemies_list)
        for enemy in enemies:
            # Если враг может ударить
            if enemy.can_attack:
                # Наносим урон игроку
                self.player.process_hit()
                # Заставляем врага перезаряжаться после удара
                enemy.reload()

                self.health_text.text = f'Здоровье: {self.player.health}'
                # Если игрок умер
                if self.player.health <= 0:
                    self.game_over_sound.play()
                    # Открываем окно проигрыша
                    lose_view = FinalView(True, self.coins_count, self.kills_count)
                    self.window.show_view(lose_view)

        # Проверяем дошел ли игрок до финиша
        finish = self.better_engine.is_on_finish()
        if finish:
            con = sqlite3.connect("player.db")
            cursor = con.cursor()

            # Начисляем монеты игроку после победы
            last_money = cursor.execute("SELECT money FROM players WHERE id = ?", (self.user_id, )).fetchone()[0]
            cursor.execute("UPDATE players SET money = ?", (self.coins_count + last_money, ))
            con.commit()

            self.win_sound.play()
            # Открываем окно победы
            win_view = FinalView(False, self.coins_count, self.kills_count)
            self.window.show_view(win_view)

        # Проверяем столкновения игрока со всеми монетами
        catched_coins = arcade.check_for_collision_with_list(self.player, self.coins_list)
        for coin in catched_coins:
            self.coin_catching_sound.play()
            self.coins_count += 1 # обновляем список собранных монет
            self.text_score.text = f"Монеты: {self.coins_count}"
            coin.remove_from_sprite_lists() # После подбора удаляем спрайт монеты

        for enemy in self.enemies_list:
            enemy.update(delta_time, self.player.center_x)

        for number in self.damage_numbers_list:
            number.update(delta_time)

        # Если игрок упал за карту - он проиграл
        if self.player.top <= 0:
            self.game_over_sound.play()

            lose_view = FinalView(True, self.coins_count, self.kills_count)
            self.window.show_view(lose_view)

        # Если спрайт верхушки лестницы существует (то есть находится в списке self.walls)
        if len(self.last_top) > 0:
            # Если игрок находится СНИЗУ верхушки - удаляем её из списка стен
            if self.player.bottom < self.last_top[0].bottom:
                # В цикле, так как может быть 1 или 2 тайла верхушки
                while self.walls[-1] in self.ladders_top:
                    self.walls.pop()
                self.last_top.clear() # В конце очищаем список

        on_ladders = False # Изначально игрок не на лестнице
        top = self.better_engine.is_on_ladder_top()
        if top:
            # Если мы попали на верхушку лестницы (дошли до конца лестницы),
            # То считаем этот спрайт, как за стену
            self.last_top = top # Сохраняем в переменную, чтобы потом удалить из списка стен
            if self.move_down:
                # Если игрок на верхушке хочет спуститься вниз -
                # удаляем спрайт верхушки из списка стен
                self.player.change_y = -4
                while self.walls[-1] in self.ladders_top:
                    self.walls.pop()
                self.last_top.clear() # В конце очищаем список

            else:
                # top может хранить 1 или 2 тайла верхушки, поэтому добавляем через цикл
                for i in range(len(top)):
                    if top[i] not in self.walls:
                        self.walls.append(top[i])
        else:
            on_ladders = self.better_engine.is_on_ladder()
            if on_ladders:
                if self.player_is_jump:
                    # Карабкаемся вверх
                    self.player.change_y = 4
                else:
                    # Если ничего не делаем - игрок медленно спускается вниз
                    self.player.change_y = -2

                if self.move_down:
                    # Если игрок хочет спуститься - ускоряем его спуск
                    self.player.change_y = -4

        camera_position = (self.player.center_x, self.player.center_y) # Обычная позиция камеры
        grounded = self.engine.can_jump(y_distance=6) and self.better_engine.can_jump()
        if grounded:
            self.time_since_grounded = 0
            # Меняем текстуру на нормальную после приземления
            if self.player.is_jump:
                # Если были в прыжке и приземлились - больше не в прыжке
                self.player.is_jump = False
                self.player.change_jump_texture()
            if self.player.is_climbing:
                # Если забирались по лестнице и столкнулись с землей - больше не забираемся
                self.player.is_climbing = False
                self.player.change_jump_texture()
        else:
            # Если игрок не на земле - он либо падает, либо поднимается по лестнице
            # Если игрок падает - не меняем положение камеры по y
            if not on_ladders:
                # Присваиваем камере положение по y, которое было, когда игрок стоял на земле
                camera_position = (self.player.center_x, self.last_y)
            else:
                # Если попали на лестницу в прыжке или другим способом
                if not self.player.is_climbing:
                    self.player.is_climbing = True
                    self.player.texture = arcade.load_texture("assets/player/climbing.png")
                    self.start_climbing_sound.play()
            # Не забываем обновить время с момента нахождения на земле
            self.time_since_grounded += delta_time

        # Если есть буфферное время (если игрок хотел прыгнуть) - уменьшаем его
        if self.jump_buffer_time > 0:
            self.jump_buffer_time -= delta_time

        want_jump = self.player_is_jump or (self.jump_buffer_time > 0)
        if want_jump:
            can_coyote = (self.time_since_grounded <= COYOTE_TIME)
            if grounded or can_coyote and not on_ladders:
                # во время прыжка оставляем камеру в неподвижном положении
                camera_position = (self.player.center_x, self.last_y)
                self.engine.jump(JUMP_SPEED)

                if not on_ladders:
                    # Если прыжок - меняем текстуру и звук на действие прыжка
                    self.player.is_jump = True
                    self.jump_sound.play()
                    self.player.change_jump_texture()
                else:
                    # Если забираемся по лестнице - меняем текстуру и звук на действие карабканья
                    self.player.is_climbing = True
                    self.player.texture = arcade.load_texture("assets/player/climbing.png")
                    self.start_climbing_sound.play()

                self.jump_buffer_time = 0
                # сбрасываем время с момента нахождения на земле
                # чтобы кайот-тайм не вызывался несколько раз
                self.time_since_grounded = 1000.0

        emitters_copy = self.emitters.copy()
        for e in emitters_copy:
            e.update(delta_time)
        for e in emitters_copy:
            if e.can_reap():
                self.emitters.remove(e)

        for bullet, trail in self.trails.items():
            trail.center_x = bullet.center_x
            trail.center_y = bullet.center_y

        self.engine.update()

        # В зависимости от уровня, после определенного расстояния, начинаем спаун врагов
        if not self.is_enemies_spawn and self.player.center_x >= 64 * self.spawn_distanation[self.level_num - 1]:
            # Спаун врагов: каждые 3.5 секунды (2.5 секунд на 3 уровне)
            arcade.schedule(self.spawn_enemies, 3.5 if self.level_num != 3 else 2.5)
            self.is_enemies_spawn = True

        # Ширина и высота экрана, не карты!
        half_view_w = self.world_camera.viewport_width / 2
        half_view_h = self.world_camera.viewport_height / 2

        # Ограничиваем позицию камеры, чтобы не показать пустоту за краями карты
        cam_x = min(self.world_width - half_view_w, max(half_view_w, camera_position[0]))
        cam_y = min(self.world_height - half_view_h, max(half_view_h, camera_position[1]))

        camera_position = (cam_x, cam_y) # Окончательная позиция камеры

        self.world_camera.position = arcade.math.lerp_2d(
            self.world_camera.position,
            camera_position,
            0.18
        )
        self.last_y = camera_position[1] # Сохраняем прошлое положение y


    def on_key_press(self, symbol: int, modifiers: int) -> EVENT_HANDLE_STATE:
        if symbol == arcade.key.F:
            self.player.make_dash()
        elif symbol == arcade.key.W:
            self.player_is_jump = True
            self.jump_buffer_time = JUMP_BUFFER
        elif symbol == arcade.key.S:
            self.move_down = True

        self.pressed_keys.add(symbol)

    def on_key_release(self, symbol: int, modifiers: int) -> EVENT_HANDLE_STATE:
        if symbol == arcade.key.W:
            self.player_is_jump = False
            # Урезаем скорость прыжка, если пользователь отпустил кнопку слишком быстро
            if self.player.change_y > 0:
                self.player.change_y *= 0.45
        elif symbol == arcade.key.S:
            self.move_down = False

        self.pressed_keys.remove(symbol)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> EVENT_HANDLE_STATE:
        if button == arcade.MOUSE_BUTTON_LEFT:
            # Проверяем кликнул ли пользователь по иконке настроек
            is_on_setting = arcade.get_sprites_at_point((x, y), self.settings)
            if is_on_setting:
                # открываем меню паузу
                pause = PauseView(self)
                self.window.show_view(pause)
            else:
                # Если нет - герой атакует
                self.player.attack(self.create_bullet)

    def create_bullet(self, center_x: float, center_y: float, direction: int):
        bullet = Bullet(center_x, center_y, direction)
        self.trails[bullet] = make_trail(bullet)
        print(self.trails)
        self.emitters.append(self.trails[bullet])
        self.bullets_list.append(bullet)

    def spawn_enemies(self, delta_time):
        enemy = Enemy(self.level_num)
        self.enemies_list.append(enemy)


class MenuView(arcade.View):
    def __init__(self):
        super().__init__()
        self.user_id = 0
        self.load_user()

        self.background_color = arcade.color.BLUE_GRAY  # Фон для меню

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout()
        self.box_layout = UIBoxLayout(vertical=True, space_between=10, height=200)

        self.setup_widgets()

        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def load_user(self):
        # Проверяем есть пользователь уже есть в системе
        if os.path.exists("local_user_id.txt"):
            with open("local_user_id.txt") as f:
                # Получаем его id
                self.user_id = int(f.readline().strip())
        else:
            # Если нет - записываем его в базу данных
            con = sqlite3.connect("player.db")
            cursor = con.cursor()
            cursor.execute("INSERT INTO players (health_level, damage_level, reload_level, money, last_level) VALUES (?, ?, ?, ?, ?)",
                           (0, 0, 0, 0, 1)) # начальные параметры игрока
            con.commit()

            user_id = cursor.lastrowid # получаем id игрока
            # Локально записываем его id в файл для будущих проверок
            with open("local_user_id.txt", "w") as f:
                f.write(str(user_id))

    def setup_widgets(self):
        play_texture = arcade.load_texture("assets/buttons/play.png")
        hovered_play_texture = arcade.load_texture("assets/buttons/hovered_play.png")
        pressed_play_texture = arcade.load_texture("assets/buttons/pressed_play.png")
        button_play = UITextureButton(texture=play_texture, texture_hovered=hovered_play_texture, texture_pressed=pressed_play_texture)
        button_play.on_click = self.start_game
        self.box_layout.add(button_play)

        shop_texture = arcade.load_texture("assets/buttons/shop.png")
        hovered_shop_texture = arcade.load_texture("assets/buttons/hovered_shop.png")
        pressed_shop_texture = arcade.load_texture("assets/buttons/pressed_shop.png")
        button_shop = UITextureButton(texture=shop_texture, texture_hovered=hovered_shop_texture, texture_pressed=pressed_shop_texture)
        button_shop.on_click = self.open_shop
        self.box_layout.add(button_shop)

        levels_texture = arcade.load_texture("assets/buttons/levels.png")
        hovered_level_texture = arcade.load_texture("assets/buttons/hovered_level.png")
        pressed_level_texture = arcade.load_texture("assets/buttons/pressed_level.png")
        button_levels = UITextureButton(texture=levels_texture, texture_hovered=hovered_level_texture, texture_pressed=pressed_level_texture)
        button_levels.on_click = self.show_levels
        self.box_layout.add(button_levels)

    def on_draw(self):
        self.clear()
        self.manager.draw()

    def start_game(self, event):
        con = sqlite3.connect("player.db")
        cursor = con.cursor()
        # Открываем последний уровень, на который зашел игрок
        last_level = cursor.execute("SELECT last_level FROM players WHERE id = ?", (self.user_id, )).fetchone()[0]
        game_view = MyGame(last_level, self.user_id)

        game_view.setup()
        self.window.show_view(game_view)

    def show_levels(self, event):
        levels_view = LevelsView(self.user_id)
        self.window.show_view(levels_view)

    def open_shop(self, event):
        shop_view = ShopView(self.user_id)
        self.window.show_view(shop_view)

    def on_hide_view(self) -> None:
        self.manager.disable()


class PauseView(arcade.View):
    def __init__(self, game_view):
        super().__init__()
        arcade.set_background_color(arcade.color.DARK_GRAY)
        self.game_view = game_view

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout(y=100)
        self.box_layout = UIBoxLayout(vertical=True, space_between=120, height=100)
        self.buttons_layout = UIBoxLayout(vertical=True, space_between=10, height=200)

        self.setup_widgets()

        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def setup_widgets(self):
        pause_texture = arcade.load_texture("assets/pause_text.png")
        pause_image = UIImage(texture=pause_texture)
        self.box_layout.add(pause_image)

        continue_texture = arcade.load_texture("assets/buttons/continue.png")
        hovered_continue_texture = arcade.load_texture("assets/buttons/hovered_continue.png")
        pressed_continue_texture = arcade.load_texture("assets/buttons/pressed_continue.png")
        button_continue = UITextureButton(texture=continue_texture, texture_hovered=hovered_continue_texture,
                                          texture_pressed=pressed_continue_texture)
        button_continue.on_click = self.return_to_game
        self.buttons_layout.add(button_continue)

        exit_texture = arcade.load_texture("assets/buttons/exit.png")
        hovered_exit_texture = arcade.load_texture("assets/buttons/hovered_exit.png")
        pressed_exit_texture = arcade.load_texture("assets/buttons/pressed_exit.png")
        button_exit = UITextureButton(texture=exit_texture, texture_hovered=hovered_exit_texture,
                                      texture_pressed=pressed_exit_texture)
        button_exit.on_click = self.go_to_menu
        self.buttons_layout.add(button_exit)

        self.box_layout.add(self.buttons_layout)

    def on_draw(self):
        self.clear()
        self.manager.draw()

    def return_to_game(self, event):
        # Возвращаем окну игры прошлый цвет фона
        self.game_view.background_color = arcade.color.BLUE_SAPPHIRE
        self.window.show_view(self.game_view)

    def go_to_menu(self, event):
        # Спрашиваем у пользователя, точно ли он хочет выйти
        message_box = UIMessageBox(
            width=300, height=200,
            message_text="Уверен, что хочешь выйти?\nПридется начинать сначала",
            buttons=("Да", "Нет")
        )
        message_box.on_action = self.on_message_button
        self.manager.add(message_box)

    def on_message_button(self, button_text):
        if button_text.action == "Да":
            menu = MenuView()
            self.window.show_view(menu)

    def on_hide_view(self) -> None:
        self.manager.disable()


class LevelsView(arcade.View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

        arcade.set_background_color(arcade.color.ANTIQUE_WHITE)

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout()
        self.box_layout = UIBoxLayout(vertical=False)

        self.setup_widgets()
        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def setup_widgets(self):
        # Иконка, чтобы выйти назад в меню
        back_texture = arcade.load_texture("assets/back_button.png")
        back_button = UITextureButton(texture=back_texture, x=15, y=515)
        back_button.on_click = self.back_to_menu
        self.manager.add(back_button)

        # Создаем 3 кнопки уровня
        for i in range(1, 4):
            level_texture = arcade.load_texture(f"assets/levels_buttons/level_{i}.png")
            btn = UITextureButton(texture=level_texture)
            btn.on_click = lambda event, level=i: self.start_selected_level(level)
            self.box_layout.add(btn)

    def back_to_menu(self, event):
        menu = MenuView()
        self.window.show_view(menu)

    def on_draw(self) -> bool | None:
        self.clear()
        self.manager.draw()

    def start_selected_level(self, level_num):
        con = sqlite3.connect("player.db")
        cursor = con.cursor()
        # Записываем текущий уровень в базу данных, чтобы потом через кнопку play его открыть
        cursor.execute("UPDATE players SET last_level = ? WHERE id = ?", (level_num, self.user_id))
        con.commit()

        # Открываем игру на заданном уровне
        game = MyGame(level_num, self.user_id)
        game.setup()
        self.window.show_view(game)

    def on_hide_view(self) -> None:
        self.manager.disable()


class ShopView(arcade.View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

        self.items = ["health", "damage", "reload"] # Названия улучшенний как в базе данных
        self.translate = ["здоровье", "урон", "перезарядку"] # Перевод названий для MessageBox
        self.prices = [15, 30, 45] # цена за 1, 2, 3 уровни

        arcade.set_background_color(arcade.color.ANTIQUE_WHITE)
        self.buy_sound = arcade.load_sound("assets/sounds/Звук покупки улучшения в магазине.mp3")

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout()
        self.box_layout = UIBoxLayout(vertical=False)

        self.setup_widgets()

        con = sqlite3.connect("player.db")
        cursor = con.cursor()
        # Загружаем количество монет пользователя из бд
        self.money_count = cursor.execute("SELECT money FROM players WHERE id = ?", (user_id, )).fetchone()[0]

        self.batch = Batch()
        # Отображаем кол-во монет
        self.money_text = arcade.Text(f"Монеты: {str(self.money_count)}", 590, 560, font_size=28,
                                      color=arcade.color.DARK_GRAY, anchor_x="left", batch=self.batch)

        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def setup_widgets(self):
        back_texture = arcade.load_texture("assets/back_button.png")
        back_button = UITextureButton(texture=back_texture, x=15, y=515)
        back_button.on_click = self.back_to_menu
        self.manager.add(back_button)

        # Создаем 3 слота улучшений: здоровье, урон, перезарядка
        for i in range(1, 4):
            con = sqlite3.connect("player.db")
            cursor = con.cursor()
            # Узнаем из базы данных уровень улучшения текущего предмета
            request = f"SELECT {self.items[i - 1]}_level FROM players WHERE id = ?"
            level = cursor.execute(request, (self.user_id, )).fetchone()[0]

            # Создаем вертикальный layout для одного слота (кнопка и полоса уровней)
            box = UIBoxLayout(vertical=True, height=150, space_between=1)

            item_texture = arcade.load_texture(f"assets/shop/item_{i}.png")
            btn = UITextureButton(texture=item_texture)
            btn.on_click = lambda event, item=(i, level): self.buy_item(item)
            box.add(btn)

            # горизонтальный layout для иконок уровней (полоса уровней, всего 3 уровня)
            item_level_row = UIBoxLayout(vertical=False, space_between=10)
            # Добавляем иконки купленных уровней
            for _ in range(level):
                level_texture = arcade.load_texture("assets/shop/bought_item.png")
                img = UIImage(texture=level_texture)
                item_level_row.add(img)

            # Потом добавляем иконки НЕкупленных уровней (оставшиеся)
            for _ in range(3 - level):
                level_texture = arcade.load_texture("assets/shop/non_bought_item.png")
                img = UIImage(texture=level_texture)
                item_level_row.add(img)

            box.add(item_level_row)
            self.box_layout.add(box)

    def on_draw(self) -> bool | None:
        self.clear()
        self.manager.draw()
        self.batch.draw()

    def back_to_menu(self, event):
        menu = MenuView()
        self.window.show_view(menu)

    def buy_item(self, selected_item: tuple[int, int]):
        # selected_item - (номер предмета, его уровень)
        # Если уже максимальный уровень - пропускаем
        if selected_item[1] == 3:
            return

        message_box = UIMessageBox(
            width=300, height=200,
            message_text=(
                f"Уверен, что хочешь улучшить {self.translate[selected_item[0] - 1]}?\n"
                f"Цена улучшения стоит {self.prices[selected_item[1]]}"
            ),
            buttons=("Да", "Нет")
        )
        message_box.on_action = lambda event: self.on_message_button(event, selected_item)
        self.manager.add(message_box)

    def on_message_button(self, button_text, selected_item):
        if button_text.action == "Да":
            # Проверяем хватает ли игроку монет, чтобы купить улучшение
            if self.money_count >= self.prices[selected_item[1]]:
                con = sqlite3.connect("player.db")
                cursor = con.cursor()

                # Меняем кол-во монет
                self.money_count -= self.prices[selected_item[1]]
                self.money_text.text = f"Монеты: {str(self.money_count)}"

                # Обновляем монеты и уровень в бд
                request = f"UPDATE players SET money = ?, {self.items[selected_item[0] - 1]}_level = ?"
                cursor.execute(request, (self.money_count, selected_item[1] + 1))
                con.commit()

                # Не забываем отобразить изменения на экране
                self.box_layout.clear()
                self.setup_widgets()

                # Звук оплаты
                self.buy_sound.play()

            else:
                # Показываем игроку, что у него нет денег
                message_box = UIMessageBox(
                    width=300, height=200, message_text="Недостаточно монет!",
                    buttons=["OK"]
                )
                # Если нажал - ничего не делаем
                message_box.on_action = lambda event: 1
                self.manager.add(message_box)

    def on_hide_view(self) -> None:
        self.manager.disable()


class FinalView(arcade.View):
    def __init__(self, game_over: bool, earned_money: int, total_kills: int):
        super().__init__()
        arcade.set_background_color(arcade.color.DARK_BLUE_GRAY if game_over else arcade.color.BABY_BLUE)
        self.game_over = game_over

        self.money = earned_money
        self.cur_money = 0 # счетчик монет
        self.kills = total_kills
        self.cur_kill = 0 # счетчик убийств врага
        self.update_text_timer = 0.1 # таймер обновления текста

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout(y=15)
        self.box_layout = UIBoxLayout(vertical=True, space_between=60)
        self.data_layout = UIBoxLayout(vertical=True, space_between=15)

        self.setup_widgets()

        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def on_update(self, delta_time: float) -> bool | None:
        # Если счетчики дошли до конца - не обновляем таймер
        if self.cur_money == self.money and self.cur_kill == self.kills:
            return

        self.update_text_timer -= delta_time
        if self.update_text_timer <= 0:
            # пока счетчики не дошли до конца, обновляем показатели в финальном окне
            if self.cur_money < self.money:
                self.cur_money += 1
                self.money_text.text = f"Монеты: {self.cur_money}"
            if self.cur_kill < self.kills:
                self.cur_kill += 1
                self.kill_text.text = f"Убийств: {self.cur_kill}"

            self.update_text_timer = 0.1

    def setup_widgets(self):
        win_texture = arcade.load_texture("assets/lose_text.png" if self.game_over else "assets/win_text.png")
        win_text = UIImage(texture=win_texture)
        self.box_layout.add(win_text)

        # Горизонтальный layout для отображения набранных монет
        row_layout = UIBoxLayout(vertical=False, space_between=15)
        coin_texture = arcade.load_texture("assets/coin.png")
        coin_icon = UIImage(texture=coin_texture)
        row_layout.add(coin_icon)

        self.money_text = UILabel("Монеты: 0", font_size=32)
        row_layout.add(self.money_text)

        self.data_layout.add(row_layout)

        # Горизонтальный layout для отображения сделанных киллов
        row_layout_2 = UIBoxLayout(vertical=False, space_between=15)
        kill_texture = arcade.load_texture("assets/kill.png")
        kill_icon = UIImage(texture=kill_texture)
        row_layout_2.add(kill_icon)

        self.kill_text = UILabel("Убийств: 0", font_size=32)
        row_layout_2.add(self.kill_text)

        self.data_layout.add(row_layout_2)
        self.box_layout.add(self.data_layout)

        # кнопка, чтобы выйти в меню
        exit_texture = arcade.load_texture("assets/buttons/menu.png")
        hovered_exit_texture = arcade.load_texture("assets/buttons/hovered_menu.png")
        pressed_exit_texture = arcade.load_texture("assets/buttons/pressed_menu.png")
        button_exit = UITextureButton(texture=exit_texture, texture_hovered=hovered_exit_texture,
                                      texture_pressed=pressed_exit_texture)
        button_exit.on_click = self.go_to_menu
        self.box_layout.add(button_exit)

    def on_draw(self) -> bool | None:
        self.clear()

        self.manager.draw()

    def go_to_menu(self, event):
        menu = MenuView()
        self.window.show_view(menu)

    def on_hide_view(self) -> None:
        self.manager.disable()


def main():
    window = arcade.Window(800, 600, "Учимся ставить на паузу")
    menu_view = MenuView()
    window.show_view(menu_view)
    arcade.run()


if __name__ == "__main__":
    main()