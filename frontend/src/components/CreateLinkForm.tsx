/**
 * Implements the [[CreateLinkForm]] component.
 * @packageDocumentation
 */

import React from 'react';
import base32 from 'hi-base32';
import moment from 'moment';
import { Form, Input, Button, DatePicker, Space, Tooltip, Spin } from 'antd';
import {
  LinkOutlined,
  MinusCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import { FormInstance } from 'antd/lib/form';
import {
  serverValidateReservedAlias,
  serverValidateDuplicateAlias,
  serverValidateLongUrl,
} from '../Validators';
import '../Base.less';
import './FixAliasRemoveButton.less';

/**
 * Displays a label with the text "Custom Alias" and a tooltip with extended help text
 * @param _props Props
 */
const CustomAliasLabel: React.FC = (_props) => {
  const customAliasHelp = `
  An alias is the shortened part of the URL. For example, for 
  the link 'go.rutgers.edu/abc123' the alias is 'abc123'. If you 
  leave it blank, Go will automatically generate an alias for you.`;
  return (
    <Tooltip title={customAliasHelp}>
      Custom Alias <QuestionCircleOutlined />
    </Tooltip>
  );
};

/**
 * Displays a label with the text "Alias" and a tooltip with extended help text for non power users
 * @param _props Props
 */
const AliasLabel: React.FC = (_props) => {
  const aliasHelp = ` 
  Aliases are automatically generated by default. You can 
  add a description for each alias you generate. Please note you 
  may only customize your aliases as a power user. Check the FAQ 
  for more info.`;
  return (
    <Tooltip title={aliasHelp}>
      Alias <QuestionCircleOutlined />
    </Tooltip>
  );
};

/**
 * The final values of the create link form
 * @interface
 */
interface CreateLinkFormValues {
  /**
   * The link title
   * @property
   */
  title: string;

  /**
   * The long URL
   * @property
   */
  long_url: string;

  /**
   * The expiration time. Absent if the link has no expiration time
   * @property
   */
  expiration_time?: moment.Moment;

  /**
   * The link's aliases. The `alias` field of an array element is absent
   * if the alias should be generated randomly by the server
   * @property
   */
  aliases: { alias?: string; description: string }[];
}

/**
 * Props for the [[CreateLinkForm]] component
 * @interface
 */
export interface Props {
  /** The user's privileges. Used to determine whether the user is allowed
   * to set custom aliases
   * @property
   */
  userPrivileges: Set<string>;

  /**
   * Callback called after the user submits the form and the new link is created
   * @property
   */
  onFinish: () => Promise<void>;
}

/**
 * State for the [[CreateLinkForm]] component
 * @interface
 */
interface State {
  loading: boolean;
}

/**
 * The [[CreateLinkForm]] component allows the user to create a new link
 * @class
 */
export class CreateLinkForm extends React.Component<Props, State> {
  formRef = React.createRef<FormInstance>();

  constructor(props: Props) {
    super(props);
    this.state = {
      loading: false,
    };
  }

  toggleLoading = () => {
    this.setState({ loading: true });
  };

  /**
   * Executes API requests to create a new link and then calls the `onFinish` callback
   * @param values The values from the form
   */
  createLink = async (values: CreateLinkFormValues): Promise<void> => {
    this.toggleLoading();

    const createLinkReq: Record<string, string> = {
      title: values.title,
      long_url: values.long_url,
    };

    if (values.expiration_time !== undefined) {
      createLinkReq.expiration_time = values.expiration_time.format();
    }

    const createLinkResp = await fetch('/api/v1/link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(createLinkReq),
    }).then((resp) => resp.json());

    const linkId: string = createLinkResp.id;

    await Promise.all(
      values.aliases.map(async (alias) => {
        const createAliasReq: any = { description: alias.description };
        let result = null;
        // Check if there are duplicate aliases
        if (alias.alias !== undefined) {
          result = await fetch(
            `/api/v1/link/validate_duplicate_alias/${base32.encode(
              alias.alias!,
            )}`,
          ).then((resp) => resp.json());
        }
        if (alias.alias !== undefined && result.valid) {
          createAliasReq.alias = alias.alias;
        }
        await fetch(`/api/v1/link/${linkId}/alias`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(createAliasReq),
        });
      }),
    );
    this.formRef.current!.resetFields();
    await this.props.onFinish();
    this.setState({ loading: false });
  };

  render(): React.ReactNode {
    const initialValues = { aliases: [{ description: '' }] };
    const mayUseCustomAliases =
      this.props.userPrivileges.has('power_user') ||
      this.props.userPrivileges.has('admin');
    return (
      <div className="dropdown-form">
        <Form
          ref={this.formRef}
          layout="vertical"
          initialValues={initialValues}
          onFinish={this.createLink}
        >
          <Form.Item
            label="Title"
            name="title"
            rules={[{ required: true, message: 'Please input a title.' }]}
          >
            <Input placeholder="Title" />
          </Form.Item>

          <Form.Item
            label="Long URL"
            name="long_url"
            rules={[
              { required: true, message: 'Please input a URL.' },
              { type: 'url', message: 'Please enter a valid URL.' },
              { validator: serverValidateLongUrl },
            ]}
          >
            <Input placeholder="Long URL" prefix={<LinkOutlined />} />
          </Form.Item>

          <Form.Item label="Expiration time" name="expiration_time">
            <DatePicker
              format="YYYY-MM-DD HH:mm:ss"
              disabledDate={(current) =>
                current && current < moment().startOf('day')
              }
              showTime={{ defaultValue: moment() }}
            />
          </Form.Item>

          <Form.List name="aliases">
            {(fields, { add, remove }) => (
              <div className="fix-alias-remove-button">
                {fields.map((field, index) => (
                  <Space
                    key={field.key}
                    style={{ display: 'flex', marginBottom: 8 }}
                    align="start"
                  >
                    {!mayUseCustomAliases ? (
                      <></>
                    ) : (
                      <Form.Item
                        label={index === 0 ? <CustomAliasLabel /> : ''}
                        name={[field.name, 'alias']}
                        fieldKey={field.fieldKey}
                        rules={[
                          {
                            min: 5,
                            message:
                              'Aliases may be no shorter than 5 characters.',
                          },
                          {
                            max: 60,
                            message:
                              'Aliases may be no longer than 60 characters.',
                          },
                          {
                            pattern: /^[a-zA-Z0-9_.,-]*$/,
                            message:
                              'Aliases may consist only of numbers, letters, and the punctuation marks “.,-_”.',
                          },
                          { validator: serverValidateReservedAlias },
                          { validator: serverValidateDuplicateAlias },
                        ]}
                      >
                        <Input
                          placeholder="alias"
                        />
                      </Form.Item>
                    )}

                    <Form.Item
                      label={
                        index === 0 ? (
                          !mayUseCustomAliases ? (
                            <AliasLabel />
                          ) : (
                            'Description'
                          )
                        ) : (
                          ''
                        )
                      }
                      name={[field.name, 'description']}
                      fieldKey={field.fieldKey}
                    >
                      <Input placeholder="Description" />
                    </Form.Item>

                    <Button
                      disabled={fields.length === 1}
                      type="text"
                      icon={<MinusCircleOutlined />}
                      onClick={() => remove(field.name)}
                    />
                  </Space>
                ))}

                <Form.Item>
                  <Button block type="dashed" onClick={add}>
                    <PlusOutlined /> Add another alias
                  </Button>
                </Form.Item>
              </div>
            )}
          </Form.List>

          <Form.Item>
            <Spin spinning={this.state.loading}>
              <Button
                type="primary"
                htmlType="submit"
                style={{ width: '100%' }}
              >
                Shrink!
              </Button>
            </Spin>
          </Form.Item>
        </Form>
      </div>
    );
  }
}
