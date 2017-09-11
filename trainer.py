import tensorflow as tf
import numpy as np
from tqdm import tqdm
from logger import Logger
import os


class Trainer:
    def __init__(self, sess, model, data_generator, config):
        self.sess = sess
        self.model = model
        self.data_generator = data_generator
        self.config = config

        self.cur_epoch_tensor = None
        self.cur_epoch_input = None
        self.cur_epoch_assign_op = None
        self.global_step_tensor = None
        self.global_step_input = None
        self.global_step_assign_op = None

        # init the global step , the current epoch and the summaries
        self.init_global_step()
        self.init_cur_epoch()

        # To initialize all variables
        self.init = tf.group(tf.global_variables_initializer(), tf.local_variables_initializer())
        self.sess.run(self.init)

        self.saver = tf.train.Saver(max_to_keep=self.config.max_to_keep)

        if not os.path.exists(self.config.summary_dir):
            os.makedirs(self.config.summary_dir)

        self.logger = Logger(sess, self.config.summary_dir)

        if self.config.load:
            self.load()

    def save(self):
        self.saver.save(self.sess, self.config.checkpoint_dir, self.global_step_tensor)
        print("Model saved")

    def load(self):
        latest_checkpoint = tf.train.latest_checkpoint(self.config.checkpoint_dir)
        if latest_checkpoint:
            print("Loading model checkpoint {} ...\n".format(latest_checkpoint))
            self.saver.restore(self.sess, latest_checkpoint)
            print("Model loaded")

    def init_cur_epoch(self):
        with tf.variable_scope('cur_epoch'):
            self.cur_epoch_tensor = tf.Variable(0, trainable=False, name='cur_epoch')
            self.cur_epoch_input = tf.placeholder('int32', None, name='cur_epoch_input')
            self.cur_epoch_assign_op = self.cur_epoch_tensor.assign(self.cur_epoch_input)

    def init_global_step(self):
        with tf.variable_scope('global_step'):
            self.global_step_tensor = tf.Variable(0, trainable=False, name='global_step')
            self.global_step_input = tf.placeholder('int32', None, name='global_step_input')
            self.global_step_assign_op = self.global_step_tensor.assign(self.global_step_input)

    def train(self):
        initial_lstm_state = np.zeros((2, self.config.batch_size, self.config.input_shape[0],
                                       self.config.input_shape[1], self.config.conv_lstm_filters))

        for epoch in range(self.cur_epoch_tensor.eval(self.sess), self.config.epochs_num):
            # Logger.info(epoch)
            losses = []

            loop = tqdm(self.data_generator.next_batch(), total=self.config.iters_per_epoch, desc="epoch-" + str(epoch) + "-")

            for itr, (warmup_batch, train_batch) in enumerate(loop):
                feed_dict = {self.model.sequences: warmup_batch,
                             self.model.initial_lstm_state: initial_lstm_state}
                lstm_state = self.sess.run(self.model.final_lstm_state, feed_dict)

                feed_dict = {self.model.sequences: train_batch, self.model.initial_lstm_state: lstm_state}
                if itr == self.config.iters_per_epoch - 1:
                    loss, _, summaries = self.sess.run([self.model.loss, self.model.optimizer, self.model.summaries], feed_dict)
                    self.logger.add_merged_summary(self.global_step_tensor.eval(self.sess), summaries)
                else:
                    loss, _ = self.sess.run([self.model.loss, self.model.optimizer], feed_dict)
                losses.append(loss)

                self.sess.run(self.global_step_assign_op, {self.global_step_input: self.global_step_tensor.eval(self.sess) + 1})

            self.logger.add_scalar_summary(self.global_step_tensor.eval(self.sess), {'train_loss': np.mean(losses)})
            self.sess.run(self.cur_epoch_assign_op, {self.cur_epoch_input: self.cur_epoch_tensor.eval(self.sess) + 1})

            self.save()

        print("Training Finished")

    def test(self, cur_it):
        initial_lstm_state = np.zeros((2, self.config.batch_size, self.config.input_shape[0],
                                       self.config.input_shape[1], self.config.conv_lstm_filters))
