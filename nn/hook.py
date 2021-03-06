import time
import numpy as np
import tensorflow as tf


class Hook(object):
    def __init__(self, verb_step):
        self.verb_step = verb_step

    def run(self, **kwargs):
        raise NotImplementedError


class ValueSummaryHook(Hook):
    """
    This hook is used to print/write value of given variables every few steps
    """
    def __init__(self, verb_step, value, value_names, print_val=None, cust_str='', log_time=False):
        """
        Initialize the hook variable
        :param verb_step: #steps between two print/write operation
        :param value: variable to be record, could be a list
        :param value_names: names of the variables, should be the same length as value
        :param print_val: which values will be print out, should be a list of indices of variables in value
                          because sometimes you want sth recorded in tensorboard but not print them, like lr
        :param cust_str: a customized appendix for the printout string
        :param log_time: if True, it will print out duration between two self.run() is called
        :param run_time: how many times to run the variable, this could be set to a large number when validation
        """
        if type(value) is not list:
            value = [value]
        self.value = value
        if type(value_names) is not list:
            value_names = [value_names]
        assert len(value_names) == len(self.value)
        self.val_names = value_names
        self.val_num = len(value)
        self.summary_op = []
        for cnt in range(self.val_num):
            self.summary_op.append(tf.summary.scalar(self.val_names[cnt], self.value[cnt]))
        if print_val is None:
            self.print_val = range(self.val_num)
        else:
            self.print_val = print_val
        cust_str += 'Step {:d}'
        for cnt in self.print_val:
            cust_str += '\t' + self.val_names[cnt] + ' {:.3f}'
        self.cust_str = cust_str
        self.log_time = log_time
        if self.log_time:
            self.time = time.time()
            self.cust_str += ', Duration: {:.3f}'
        super().__init__(verb_step)

    def run(self, step, sess, summary_writer=None):
        """
        :param step: The current global step number
        :param sess: session to run the summary writer
        :param summary_writer: summary writer
        :return:
        """
        if step % self.verb_step == 0:
            value = []
            for cnt in range(len(self.value)):
                value.append(sess.run(self.value[cnt]))
            print_value = [value[x] for x in self.print_val]
            if not self.log_time:
                print(self.cust_str.format(step, *print_value))
            else:
                curr_time = time.time()
                print(self.cust_str.format(step, *print_value, curr_time - self.time))
                self.time = curr_time
            if summary_writer is not None:
                for cnt, s in enumerate(self.summary_op):
                    summary = sess.run(s, feed_dict={self.value[cnt]: value[cnt]})
                    summary_writer.add_summary(summary, step)
                summary_writer.flush()


class ValueSummaryHookIters(Hook):
    """
    This hook is used to print/write value of given variables every few steps over few iterations
    This is useful for having stable values
    """
    def __init__(self, verb_step, value, value_names, print_val=None, cust_str='', log_time=False, run_time=1):
        """
        Initialize the hook variable
        :param verb_step: #steps between two print/write operation
        :param value: variable to be record, could be a list
        :param value_names: names of the variables, should be the same length as value
        :param print_val: which values will be print out, should be a list of indices of variables in value
                          because sometimes you want sth recorded in tensorboard but not print them, like lr
        :param cust_str: a customized appendix for the printout string
        :param log_time: if True, it will print out duration between two self.run() is called
        :param run_time: how many times to run the variable, this could be set to a large number when validation
        """
        if type(value) is not list:
            value = [value]
        self.value = value
        if type(value_names) is not list:
            value_names = [value_names]
        assert len(value_names) == len(self.value)
        self.val_names = value_names
        self.val_num = len(value)
        self.summary_op = []
        for cnt in range(self.val_num):
            self.summary_op.append(tf.summary.scalar(self.val_names[cnt], self.value[cnt][0]))
        if print_val is None:
            self.print_val = range(self.val_num)
        else:
            self.print_val = print_val
        cust_str += 'Step {:d}'
        for cnt in self.print_val:
            cust_str += '\t' + self.val_names[cnt] + ' {:.3f}'
        self.cust_str = cust_str
        self.log_time = log_time
        if self.log_time:
            self.time = time.time()
            self.cust_str += ', Duration: {:.3f}'
        self.run_time = run_time
        self.reset_op = [v[2] for v in self.value]
        super().__init__(verb_step)

    def run(self, step, sess, summary_writer=None):
        """
        :param step: The current global step number
        :param sess: session to run the summary writer
        :param summary_writer: summary writer
        :return:
        """
        if step % self.verb_step == 0:
            sess.run(self.reset_op)
            for _ in range(self.run_time):
                try:
                    sess.run([v[1] for v in self.value])
                except tf.errors.OutOfRangeError:
                    break
            value = sess.run([v[0] for v in self.value])
            print_value = [value[x] for x in self.print_val]
            if not self.log_time:
                print(self.cust_str.format(step, *print_value))
            else:
                curr_time = time.time()
                print(self.cust_str.format(step, *print_value, curr_time - self.time))
                self.time = curr_time
            if summary_writer is not None:
                for cnt, s in enumerate(self.summary_op):
                    summary = sess.run(s, feed_dict={self.value[cnt][0]: value[cnt]})
                    summary_writer.add_summary(summary, step)
                summary_writer.flush()


class ImageValidSummaryHook(Hook):
    """
    Record validation image in tensorboard
    """
    def __init__(self, input_size, verb_step, feature, label, pred, summary_func, value=None,
                 name='Validation_Image', max_output=5, img_mean=np.zeros(3)):
        """
        Initialize the object
        :param verb_step: #steps between two print/write operation
        :param value: a h*w*3 variable to save the validation image
        :param feature: input rgb image
        :param label: input ground truth
        :param pred: prediction generated by network
        :param summary_func: function that pad and concatenate the predictions
        :param name: name of this summary operation
        :param max_output: maximum number of images to show in the tensorboard
        :param img_mean:
        """
        if value is None:
            name='valid_images'
            if int(input_size[1]) / int(input_size[0]) > 1.5:
                # if image is too wide, concatenate them horizontally
                value = tf.placeholder(tf.uint8, shape=[None, input_size[0] * 3, input_size[1], 3], name=name)
            else:
                value = tf.placeholder(tf.uint8, shape=[None, input_size[0], input_size[1] * 3, 3], name=name)
        self.value = value
        self.summary_op = tf.summary.image(name, self.value, max_outputs=max_output)
        self.feature = feature
        self.label = label
        self.pred = pred
        self.summary_func = summary_func
        self.img_mean = img_mean
        super().__init__(verb_step)

    def run(self, step, sess, summary_writer):
        """
        :param step: The current global step number
        :param sess: session to run the summary writer
        :param summary_writer: summary writer
        :return:
        """
        if step % self.verb_step == 0:
            feature, label, pred = sess.run([self.feature, self.label, self.pred])
            summary = sess.run(self.summary_op, feed_dict={self.value: self.summary_func(feature[:, :, :, :3],
                                                                                         label, pred, self.img_mean)})
            summary_writer.add_summary(summary, step)
            summary_writer.flush()


class IoUSummaryHook(Hook):
    """
    Print/Write IoU
    """
    def __init__(self, verb_step, value, value_names='IoU', cust_str='', log_time=False, run_time=1):
        """
        Initialize the object
        :param verb_step: #steps between two print/write operation
        :param value: the network.loss_iou variable
        :param value_names: name of the summary operation
        :param cust_str: a customized appendix for the printout string
        :param log_time: if True, it will print out duration between two self.run() is called
        :param run_time: how many times to run the variable, this could be set to a large number when validation
        """
        self.value = value
        self.val_names = value_names
        self.valid_iou = tf.placeholder(tf.float32, [])
        self.summary_op = tf.summary.scalar(self.val_names, self.valid_iou)
        cust_str += 'Step {:d}\t' + self.val_names + ' {:.3f}'
        self.cust_str = cust_str
        self.log_time = log_time
        if self.log_time:
            self.time = time.time()
            self.cust_str += ', Duration: {:.3f}'
        self.run_time = run_time
        super().__init__(verb_step)

    def run(self, step, sess, summary_writer=None):
        """
        :param step: The current global step number
        :param sess: session to run the summary writer
        :param summary_writer: summary writer
        :return:
        """
        if step % self.verb_step == 0:
            val_mean = np.zeros(2)
            for _ in range(self.run_time):
                try:
                    val_mean += sess.run(self.value)
                except tf.errors.OutOfRangeError:
                    break
            value = val_mean / self.run_time
            iou = value[0] / value[1]
            if not self.log_time:
                print(self.cust_str.format(step, iou))
            else:
                curr_time = time.time()
                print(self.cust_str.format(step, iou, curr_time-self.time))
                self.time = curr_time
            if summary_writer is not None:
                summary = sess.run(self.summary_op, feed_dict={self.valid_iou: iou})
                summary_writer.add_summary(summary, step)
                summary_writer.flush()


class ModelSaveHook(Hook):
    """
    Save the model every few steps
    """
    def __init__(self, verb_step, ckdir, max_to_keep=None):
        """
        Initialize the object
        :param verb_step: #steps between two print/write operation
        :param ckdir: checkpoint directory to save the model
        :param max_to_keep: maximum number of ckpts to be saved
        """
        self.saver = tf.train.Saver(var_list=tf.global_variables(), max_to_keep=max_to_keep)
        self.ckdir = ckdir
        super().__init__(verb_step)

    def run(self, step, sess, summary_writer=None):
        """
        :param step: The current global step number
        :param sess: session to run the summary writer
        :param summary_writer: summary writer
        :return:
        """
        if step % self.verb_step == 0:
            self.saver.save(sess, '{}/model_{}.ckpt'.format(self.ckdir, step // self.verb_step), global_step=step)
